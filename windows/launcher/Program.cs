using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace VillageLife;

internal static class Program {
    [STAThread]
    static void Main() {
        ApplicationConfiguration.Initialize();
        Application.Run(new ManagerWindow());
    }
}

public sealed class ManagerWindow : Form {
    readonly string root = Directory.GetParent(AppContext.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar))?.FullName ?? AppContext.BaseDirectory;
    readonly TextBox output = new() {Multiline=true, ReadOnly=true, ScrollBars=ScrollBars.Vertical,
        Dock=DockStyle.Fill, Font=new Font("Consolas", 10), WordWrap=false};
    readonly FlowLayoutPanel bar = new() {Dock=DockStyle.Top, Height=132, AutoScroll=true, WrapContents=true};
    readonly HttpClient http = new() {Timeout=TimeSpan.FromSeconds(3)};
    Process? backend;
    bool closing;
    string ServerExe => Path.Combine(root, "bin", "VillageLifeServer", "VillageLifeServer.exe");

    public ManagerWindow() {
        Text="Village Life Revival | New Backend Test Manager"; Width=940; Height=660;
        StartPosition=FormStartPosition.CenterScreen;
        Controls.Add(output); Controls.Add(bar);
        Add("Start new backend", async()=>await StartBackend());
        Add("Stop backend", async()=>await StopBackend());
        Add("Check API", async()=>await HealthCheck());
        Add("Select BlueStacks instance", async()=>await ChooseInstance());
        Add("Verify selection", async()=>await RunTool("verify-instance"));
        Add("Start selected instance", async()=>await RunTool("start-instance"));
        Add("Check ADB", async()=>await RunTool("adb-check"));
        Add("Network diagnostics", async()=>await RunTool("network-report"));
        Add("Open instance manager", async()=>await RunTool("open-instance-manager"));
        Add("Dry-run save migration", async()=>await DryRunMigration());
        Add("Export missing requests", async()=>await RunTool("export-missing-requests"));
        Add("Export support report", async()=>await ExportSupport());
        Add("About game compatibility", async()=>{ Log("[VL-PROTOCOL-NOT-READY] This NEW backend exposes /v1, not the original APK's binary ClientService protocol. Original APK play is disabled in this test manager. No old backend fallback exists."); await Task.CompletedTask; });
        FormClosing += async (_, e) => {if(!closing && backend is {HasExited:false}) {e.Cancel=true; closing=true; await StopBackend(); Close();}};
        Log("New-backend-only test manager. No legacy 2.11 executable, fallback, bundled XAPK or auto-migration.");
        Log("Data lives in %LOCALAPPDATA%\\VillageLifeRevivalNext, outside the installation folder.");
        if (!File.Exists(ServerExe)) Log("[VL-BUILD-INCOMPLETE] Missing bundled server: "+ServerExe);
    }

    void Add(string caption, Func<Task> action) {
        var b = new Button {Text=caption, Width=173, Height=35, Margin=new Padding(6,5,3,3)};
        b.Click+=async(_,_)=>{b.Enabled=false; try {await action();} catch(Exception ex){Log("[VL-TOOL-FAILED] "+ex.GetType().Name+": "+ex.Message);} finally {if(!IsDisposed)b.Enabled=true;}};
        bar.Controls.Add(b);
    }
    void Log(string line) {
        if(IsDisposed) return;
        if(InvokeRequired) {try{BeginInvoke(()=>Log(line));}catch(InvalidOperationException){} return;}
        output.AppendText(DateTime.Now.ToString("HH:mm:ss")+"  "+line+Environment.NewLine);
    }
    ProcessStartInfo Command(params string[] args) {
        if(!File.Exists(ServerExe)) throw new FileNotFoundException("Bundled NEW backend missing. Rebuild test installer",ServerExe);
        var info = new ProcessStartInfo(ServerExe) {WorkingDirectory=root,UseShellExecute=false,
            RedirectStandardOutput=true,RedirectStandardError=true,CreateNoWindow=true,
            StandardOutputEncoding=Encoding.UTF8,StandardErrorEncoding=Encoding.UTF8};
        foreach(var arg in args) info.ArgumentList.Add(arg);
        info.Environment["PYTHONIOENCODING"]="utf-8:replace";
        info.Environment["PYTHONUTF8"]="1";
        return info;
    }
    async Task<(int code,string stdout,string stderr)> CommandOnce(int timeoutSeconds,params string[] args) {
        using var process=Process.Start(Command(args)) ?? throw new IOException("Unable to launch backend tool");
        var stdout=process.StandardOutput.ReadToEndAsync();
        var stderr=process.StandardError.ReadToEndAsync();
        using var deadline=new CancellationTokenSource(TimeSpan.FromSeconds(timeoutSeconds));
        try{await process.WaitForExitAsync(deadline.Token);}
        catch(OperationCanceledException){process.Kill(entireProcessTree:true);await process.WaitForExitAsync();throw new TimeoutException("[VL-TOOL-TIMEOUT] Tool exceeded "+timeoutSeconds+" seconds");}
        return (process.ExitCode,await stdout,await stderr);
    }
    async Task RunTool(params string[] args) {
        var (code, stdout, stderr)=await CommandOnce(30,args);
        if(stdout.Trim().Length>0) Log(stdout.Trim());
        if(code!=0) Log("[VL-TOOL-ERROR] "+stderr.Trim());
    }
    async Task StartBackend() {
        if(backend is {HasExited:false}){Log("[VL-SERVER-ALREADY-RUNNING] Backend is already running");return;}
        backend=Process.Start(Command("serve","--port","8765")) ?? throw new IOException("Unable to start new backend");
        var proc=backend;
        _=Task.Run(async()=>{try{while(await proc.StandardOutput.ReadLineAsync() is string line)Log(line);}catch(IOException){}});
        _=Task.Run(async()=>{try{while(await proc.StandardError.ReadLineAsync() is string line)Log(line);}catch(IOException){}});
        _=Task.Run(async()=>{await proc.WaitForExitAsync();Log("[VL-SERVER-EXIT] New backend exited with code "+proc.ExitCode);});
        await Task.Delay(600);
        await HealthCheck();
    }
    async Task StopBackend(){
        var proc=backend; if(proc is null || proc.HasExited){Log("Backend is not running");return;}
        try{proc.Kill(entireProcessTree:true); await proc.WaitForExitAsync();Log("New backend stopped");}
        catch(Exception ex){Log("[VL-SERVER-STOP-FAILED] "+ex.Message);}
    }
    async Task HealthCheck(){
        try{var response=await http.GetAsync("http://127.0.0.1:8765/health");Log("New API status: "+(int)response.StatusCode+" "+await response.Content.ReadAsStringAsync());}
        catch(HttpRequestException){Log("[VL-SERVER-OFFLINE] New backend is not responding on 127.0.0.1:8765");}
        catch(TaskCanceledException){Log("[VL-SERVER-TIMEOUT] New backend health check timed out");}
    }
    sealed record InstanceOption(string id,string display_name,int adb_port,int? live_adb_port);
    async Task ChooseInstance() {
        var (code,stdout,stderr)=await CommandOnce(20,"list-instances");
        if(code!=0) {Log("[VL-BS-LIST-FAILED] "+stderr.Trim());return;}
        var options=JsonSerializer.Deserialize<InstanceOption[]>(stdout) ?? Array.Empty<InstanceOption>();
        if(options.Length==0){Log("[VL-BS-NO-PIE64] No Pie64 instance found. Open BlueStacks Multi-instance Manager first.");return;}
        using var dialog=new Form {Text="Choose dedicated Village Life instance",Width=640,Height=230,StartPosition=FormStartPosition.CenterParent};
        var combo=new ComboBox {Left=20,Top=60,Width=580,DropDownStyle=ComboBoxStyle.DropDownList};
        combo.Items.AddRange(Array.ConvertAll(options, x => (object)$"{x.display_name} [{x.id}]  ADB {x.adb_port}"));
        var btn=new Button {Text="Bind exact instance",Left=395,Top=113,Width=205,DialogResult=DialogResult.OK,Enabled=false};
        combo.SelectedIndexChanged+=(_,_)=>btn.Enabled=combo.SelectedIndex>=0;
        dialog.Controls.AddRange(new Control[]{new Label {Text="Select explicitly. No silent fallback to the default instance.",Left=20,Top=20,Width=580},combo,btn});
        if(dialog.ShowDialog(this)!=DialogResult.OK || combo.SelectedIndex<0) return;
        Log("Binding selected instance "+options[combo.SelectedIndex].id);
        await RunTool("bind-instance",options[combo.SelectedIndex].id);
    }
    async Task DryRunMigration(){
        using var pick=new FolderBrowserDialog {Description="Select a COPY of your old 2.11 backend/private_state folder. This is dry-run only."};
        if(pick.ShowDialog(this)!=DialogResult.OK)return;
        await RunTool("import-legacy", pick.SelectedPath);
        Log("Dry run finished. Nothing in the selected old saves was changed; no new import was applied.");
    }
    async Task ExportSupport(){
        using var save=new SaveFileDialog {Filter="ZIP file (*.zip)|*.zip",FileName="villagelife-support.zip"};
        if(save.ShowDialog(this)!=DialogResult.OK)return;
        await RunTool("export-support",save.FileName);
        Log("Inspect the report before sharing. Saves, request bodies, and credentials are excluded.");
    }
}
