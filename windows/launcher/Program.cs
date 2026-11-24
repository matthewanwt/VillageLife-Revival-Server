using System.Diagnostics;
using System.Drawing;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Windows.Forms;

namespace VillageLife;
internal static class Program {
    [STAThread] static void Main() {
        ApplicationConfiguration.Initialize();
        string profile=Path.GetDirectoryName(VillageLifeWindow.DefaultDatabase())!.ToUpperInvariant();
        string key=Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(Encoding.UTF8.GetBytes(profile)));
        using var lease=new Mutex(true,@"Local\VillageLifeProfile-"+key,out bool created);
        if(!created){MessageBox.Show("Village Life is already open for this save folder. Use that launcher or close it before opening another.","Village Life");return;}
        using var installerMarker=new Mutex(false,@"Local\VillageLifeLauncherActive");
        try { Application.Run(new VillageLifeWindow()); }
        finally { lease.ReleaseMutex(); }
    }
}

public sealed partial class VillageLifeWindow : Form {
    const string ReleaseVersion = "0.4.1";
#if PRIVATE_CANDIDATE
    const string ReleaseTitle = "Village Life — Private Audit Candidate";
    const string DataFolder = "VillageLifeAuditPrivate";
#else
    const string ReleaseTitle = "Village Life Community Update " + ReleaseVersion;
    const string DataFolder = "VillageLifeRevivalNext";
#endif
    sealed class Settings { public string GameTables { get; set; }=""; public string Xapk { get; set; }=""; public string Inventory { get; set; }=""; public string? Obb { get; set; } public int Port { get; set; }=80; public bool ClientPrepared { get; set; } public bool PreparedFilesReady { get; set; } public bool VillageChoiceMade { get; set; } public string ImportedVillage { get; set; }=""; public string LocalVillage { get; set; }=""; }
    readonly string root=Directory.GetParent(AppContext.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar))?.FullName??AppContext.BaseDirectory;
    internal static string DefaultDatabase() {
        var alternate = Environment.GetEnvironmentVariable("VILLAGELIFE_DB");
        return string.IsNullOrWhiteSpace(alternate)
            ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),DataFolder,"worlds.sqlite3")
            : Path.GetFullPath(alternate);
    }
    readonly string defaultDatabase=DefaultDatabase();
    string state=>Path.GetDirectoryName(defaultDatabase)!;
    readonly TextBox output=new(){Multiline=true,ReadOnly=true,ScrollBars=ScrollBars.Vertical,Dock=DockStyle.Fill,Font=new Font("Consolas",10),WordWrap=false};
    readonly Label stage=new(){Dock=DockStyle.Bottom,Height=25,Padding=new Padding(8,4,0,0),Text="Click Play to start or resume setup."};
    readonly ProgressBar progress=new(){Dock=DockStyle.Bottom,Height=16,Minimum=0,Maximum=100,Value=0};
    readonly HttpClient http=new(){Timeout=TimeSpan.FromSeconds(4)}; readonly List<Button> actions=new(); Process? backend; bool closing,busy;
    readonly CancellationTokenSource lifetime=new();
    CancellationTokenSource? setupStep;
    readonly HashSet<Process> ownedTools=new();
    readonly OwnedProcessJob processJob=new();
    readonly System.Threading.Channels.Channel<string> pendingLogs=System.Threading.Channels.Channel.CreateBounded<string>(
        new System.Threading.Channels.BoundedChannelOptions(2000){FullMode=System.Threading.Channels.BoundedChannelFullMode.DropOldest,SingleReader=true});
    readonly System.Windows.Forms.Timer logFlush=new(){Interval=200};
    string verifiedExpansion="";
    string ServerExe=>Path.Combine(root,"bin","VillageLifeServer","VillageLifeServer.exe"); string SettingsFile=>Path.Combine(state,"launcher-settings.json");
    string BundledGame=>Path.Combine(root,"game-assets","Village-Life-Original.xapk");
    string PrivateAssets=>Path.Combine(root,"private-assets");
    string SigningJdkHome=>Path.Combine(root,"signing-tools","jdk");
    public VillageLifeWindow() {
        BuildDashboard();
        FormClosing+=async(_,e)=>{
            if (closing) return;
            closing=true;
            lifetime.Cancel();
            if (e.CloseReason==CloseReason.WindowsShutDown) return;
            e.Cancel=true;
            try { await Stop(); }
            finally { Close(); }
        };
        gameMonitor.Tick+=CheckGameClosed;
        logFlush.Tick+=(_,_)=>FlushLogs();logFlush.Start();
        Shown+=async(_,_)=>await RunAction("Refresh village details",RefreshVillageDetails);
        FormClosed+=(_,_)=>{gameMonitor.Dispose();logFlush.Dispose();dashboardClock.Dispose();lifetime.Cancel();processJob.Dispose();};
        Log(ReleaseTitle);Log("Click Play. Village Life will guide you through any steps still needed.");
        if(!File.Exists(ServerExe))Log("[VL-BUILD-INCOMPLETE] Bundled server missing: "+ServerExe);
    }
    void Log(string value){if(!IsDisposed)pendingLogs.Writer.TryWrite(DateTime.Now.ToString("HH:mm:ss")+"  "+value+Environment.NewLine);}
    void FlushLogs(){
        var text=new StringBuilder();
        for(int count=0;count<200 && pendingLogs.Reader.TryRead(out var line);count++)text.Append(line);
        if(text.Length==0)return;
        output.AppendText(text.ToString());
        if(output.TextLength>200_000){output.Select(0,output.TextLength-150_000);output.SelectedText="";output.SelectionStart=output.TextLength;output.ScrollToCaret();}
        try {
            string logs=Path.Combine(state,"logs");Directory.CreateDirectory(logs);string file=Path.Combine(logs,"launcher.log");
            if(File.Exists(file)&&new FileInfo(file).Length>2_000_000){File.Move(file+".1",file+".2",true);}
        } catch(FileNotFoundException){} catch(IOException){} catch(UnauthorizedAccessException){}
        try {
            string file=Path.Combine(state,"logs","launcher.log");
            if(File.Exists(file)&&new FileInfo(file).Length>2_000_000)File.Move(file,file+".1",true);
            File.AppendAllText(file,text.ToString());
        } catch(IOException){} catch(UnauthorizedAccessException){}
    }
    void SetStage(int value,string text){if(IsDisposed)return;if(InvokeRequired){BeginInvoke(()=>SetStage(value,text));return;}progress.Value=Math.Clamp(value,0,100);stage.Text=text;UpdateDashboardStatus(text);}
    Settings Read(){try{return JsonSerializer.Deserialize<Settings>(File.ReadAllText(SettingsFile))??new();}catch{return new();}}
    void Write(Settings s) {
        Directory.CreateDirectory(state);
        var pending=SettingsFile+"."+Guid.NewGuid().ToString("N")+".pending";
        try {
            using (var file=File.Create(pending)) {
                JsonSerializer.Serialize(file,s,new JsonSerializerOptions{WriteIndented=true});
                file.Flush(flushToDisk:true);
            }
            File.Move(pending,SettingsFile,true);
        } finally { File.Delete(pending); }
    }
    ProcessStartInfo Command(params string[] args){if(!File.Exists(ServerExe))throw new FileNotFoundException("Bundled new backend missing",ServerExe);var p=new ProcessStartInfo(ServerExe){WorkingDirectory=root,UseShellExecute=false,RedirectStandardOutput=true,RedirectStandardError=true,CreateNoWindow=true,StandardOutputEncoding=Encoding.UTF8,StandardErrorEncoding=Encoding.UTF8};foreach(var a in args)p.ArgumentList.Add(a);p.Environment["PYTHONUTF8"]="1";p.Environment["VILLAGELIFE_DB"]=defaultDatabase;return p;}
    async Task<(int,string,string)> Once(int seconds,params string[] args){
        lifetime.Token.ThrowIfCancellationRequested();
        using var p=Process.Start(Command(args))??throw new IOException("Could not start backend tool");
        try { processJob.Add(p); } catch { if(!p.HasExited)p.Kill(true);throw; }
        ownedTools.Add(p);
        var o=p.StandardOutput.ReadToEndAsync();var e=p.StandardError.ReadToEndAsync();
        var stepToken=setupStep?.Token??CancellationToken.None;
        using var deadline=CancellationTokenSource.CreateLinkedTokenSource(lifetime.Token,stepToken);
        deadline.CancelAfter(TimeSpan.FromSeconds(seconds));
        try { await p.WaitForExitAsync(deadline.Token);return(p.ExitCode,await o,await e); }
        catch(OperationCanceledException){
            try { if(!p.HasExited)p.Kill(true);await p.WaitForExitAsync(); } catch(InvalidOperationException){}
            if(lifetime.IsCancellationRequested||stepToken.IsCancellationRequested)throw;
            throw new TimeoutException("[VL-TOOL-TIMEOUT]");
        } finally { ownedTools.Remove(p); }
    }
    async Task Tool(params string[] args){var r=await Once(300,args);if(!string.IsNullOrWhiteSpace(r.Item2))Log(r.Item2.Trim());if(r.Item1!=0)throw new InvalidOperationException(string.IsNullOrWhiteSpace(r.Item3)?"[VL-TOOL-ERROR] Tool failed":r.Item3.Trim());}
    async Task ToolQuiet(params string[] args){var r=await Once(300,args);if(r.Item1!=0)throw new InvalidOperationException(string.IsNullOrWhiteSpace(r.Item3)?"[VL-TOOL-ERROR] Tool failed":r.Item3.Trim());}
    async Task ToolQuietWithin(int seconds,params string[] args){var r=await Once(seconds,args);if(r.Item1!=0)throw new InvalidOperationException(string.IsNullOrWhiteSpace(r.Item3)?"[VL-TOOL-ERROR] Tool failed":r.Item3.Trim());}
    bool Ready(Settings s)=>File.Exists(s.GameTables)&&File.Exists(s.Xapk)&&File.Exists(s.Inventory)&&File.Exists(s.Obb)&&s.ClientPrepared;
    void ChooseGameArchive(Settings s) {
        var bundled = Directory.Exists(PrivateAssets) ? Directory.GetFiles(PrivateAssets,"*.xapk") : Array.Empty<string>();
        if (File.Exists(BundledGame)) {
            s.Xapk = BundledGame;
        } else if (bundled.Length == 1) {
            s.Xapk = bundled[0];
        } else {
            using var picker = new OpenFileDialog {Title="Select your original Village Life XAPK",
                Filter="Village Life XAPK (*.xapk)|*.xapk", CheckFileExists=true};
            if (File.Exists(s.Xapk)) picker.InitialDirectory=Path.GetDirectoryName(s.Xapk);
            if (picker.ShowDialog(this)!=DialogResult.OK) throw new OperationCanceledException();
            s.Xapk=picker.FileName;
        }
        if (!File.Exists(Path.Combine(SigningJdkHome,"bin","keytool.exe")) ||
            !File.Exists(Path.Combine(SigningJdkHome,"bin","jarsigner.exe")))
            throw new InvalidOperationException("[VL-SIGNER-MISSING] Bundled Java signing tools are missing.");
    }
    string VillageDatabase(Settings settings) {
        if (string.IsNullOrEmpty(settings.ImportedVillage)) return defaultDatabase;
        if (!System.Text.RegularExpressions.Regex.IsMatch(settings.ImportedVillage, @"\A[0-9a-f]{64}\z"))
            throw new InvalidOperationException("Choose a village again.");
        var path = Path.Combine(state,"imported-villages",settings.ImportedVillage+".sqlite3");
        if (!File.Exists(path)) throw new InvalidOperationException("The imported village file is missing. Check your backups or choose another village.");
        return path;
    }
    void RequireStopped() {
        if (backend is {HasExited:false}) throw new InvalidOperationException("Click Stop before changing your village or setup.");
    }
    async Task<JsonDocument> ReadVillageList(params string[] args) {
        var result = await Once(60,args);
        if (result.Item1 != 0) throw new InvalidOperationException(result.Item3.Trim());
        return JsonDocument.Parse(result.Item2);
    }
    static string VillageLabel(JsonElement village) {
        var name = village.GetProperty("name").GetString() ?? "Village";
        int level = village.GetProperty("level").GetInt32();
        string gems = village.GetProperty("gems").ValueKind == JsonValueKind.Null
            ? "" : $", {village.GetProperty("gems").GetInt64():N0} gems";
        int villagers = village.GetProperty("villagers").GetInt32();
        string examples = village.TryGetProperty("examples",out var people) && people.GetArrayLength()>0
            ? " — "+string.Join(", ",people.EnumerateArray().Select(person=>person.GetString())) : "";
        return level == 0 ? $"{name} ({villagers} villagers)" : $"{name} (level {level}{gems}, {villagers} villagers){examples}";
    }
    int PickVillage(string title, string detail, string[] choices, int initial = 0) {
        using var dialog = new Form {Text=title, StartPosition=FormStartPosition.CenterParent,
            FormBorderStyle=FormBorderStyle.FixedDialog, MaximizeBox=false, MinimizeBox=false,
            AutoScaleMode=AutoScaleMode.Font, AutoSize=true, AutoSizeMode=AutoSizeMode.GrowAndShrink};
        var layout = SetupDialogLayout(620);
        var items = new ComboBox {Dock=DockStyle.Top, DropDownStyle=ComboBoxStyle.DropDownList};
        items.Items.AddRange(choices);
        items.SelectedIndex = initial;
        var select = SetupButton("Continue",DialogResult.OK);
        select.Enabled=initial>=0;
        items.SelectedIndexChanged+=(_,_)=>select.Enabled=items.SelectedIndex>=0;
        var cancel = SetupButton("Cancel",DialogResult.Cancel);
        layout.Controls.Add(SetupText(detail,620));
        layout.Controls.Add(items);
        layout.Controls.Add(SetupButtons(cancel,select));
        dialog.Controls.Add(layout);
        dialog.AcceptButton=select;
        dialog.CancelButton=cancel;
        return dialog.ShowDialog(this)==DialogResult.OK ? items.SelectedIndex : -1;
    }

    static TableLayoutPanel SetupDialogLayout(int width) {
        var panel=new TableLayoutPanel {
            AutoSize=true, AutoSizeMode=AutoSizeMode.GrowAndShrink, ColumnCount=1,
            MinimumSize=new Size(width+36,0), Padding=new Padding(18), Dock=DockStyle.Fill
        };
        panel.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));
        return panel;
    }

    static Label SetupText(string text,int width) => new() {
        Text=text, AutoSize=true, MaximumSize=new Size(width,0), Margin=new Padding(3,3,3,12)
    };

    static Button SetupButton(string text,DialogResult result=DialogResult.None) {
        var button=new Button {
            Text=text, AutoSize=true, AutoSizeMode=AutoSizeMode.GrowAndShrink,
            MinimumSize=new Size(100,32), Padding=new Padding(8,3,8,3), DialogResult=result
        };
        return button;
    }

    static FlowLayoutPanel SetupButtons(params Control[] buttons) {
        var panel=new FlowLayoutPanel {
            AutoSize=true, AutoSizeMode=AutoSizeMode.GrowAndShrink, Dock=DockStyle.Top,
            FlowDirection=FlowDirection.RightToLeft, WrapContents=false, Margin=new Padding(0,10,0,0)
        };
        panel.Controls.AddRange(buttons);
        return panel;
    }
    async Task<bool> ImportLegacy() {
        RequireStopped();
        using var picker = new FolderBrowserDialog {
            Description="Select the old 0.2.6 installation or its backend/private_state backup. Close its game and launcher first.",
            UseDescriptionForTitle=true, ShowNewFolderButton=false
        };
        if (picker.ShowDialog(this)!=DialogResult.OK) return false;
        using var preview = await ReadVillageList("preview-legacy-villages",picker.SelectedPath);
        var candidates = preview.RootElement.GetProperty("villages").EnumerateArray().ToArray();
        int skipped = preview.RootElement.GetProperty("skipped").GetInt32();
        if (candidates.Length==0) {
            string reason=skipped>0
                ? string.Join(" ",preview.RootElement.GetProperty("errors").EnumerateArray().Select(error=>error.GetString()))
                : "No matching 0.2.6 save and profile files were found. Extract the ZIP first, then select its private_state folder or the old installation folder.";
            throw new InvalidOperationException(reason);
        }
        string detail = $"Copy from {picker.SelectedPath}\nThe launcher backs up the playable copy before launch. Open Save Backups to find it.";
        if (skipped>0) detail += $" Skipped {skipped} unreadable or unsupported save(s).";
        int chosen = PickVillage("Import 0.2.6 Save",detail,candidates.Select(VillageLabel).ToArray());
        if (chosen<0) return false;
        var entry = candidates[chosen];
        var key = entry.GetProperty("key").GetString()!;
        await ToolQuiet("copy-legacy-village",picker.SelectedPath,key,entry.GetProperty("fingerprint").GetString()!);
        var settings = Read();
        settings.ImportedVillage=key;
        settings.LocalVillage="";
        Write(settings);
        Log("Selected imported village: "+VillageLabel(entry));
        return true;
    }
    async Task ChooseVillage() {
        RequireStopped();
        using var list = await ReadVillageList("list-legacy-villages");
        var copies = list.RootElement.EnumerateArray().ToArray();
        using var localList = File.Exists(defaultDatabase)
            ? await ReadVillageList("--db",defaultDatabase,"list-gem-villages") : null;
        var local = localList?.RootElement.EnumerateArray().ToArray() ?? [];
        var settings = Read();
        var choices = new List<(string Label,string Imported,string Local)> {
            ("Use the village linked to the selected BlueStacks instance","","")
        };
        choices.AddRange(local.Select(row=>(
            LocalVillageLabel(row),"",row.GetProperty("village_id").GetString()!)));
        choices.AddRange(copies.Select(row=>(
            "Imported from 0.2.6 — "+VillageLabel(row),row.GetProperty("key").GetString()!,"")));
        int initial=choices.FindIndex(choice=>choice.Imported==settings.ImportedVillage && choice.Local==settings.LocalVillage);
        int picked = PickVillage("Choose Village","Select a saved village to open on the selected BlueStacks instance when you click Play.",
                                 choices.Select(choice=>choice.Label).ToArray(),Math.Max(0,initial));
        if (picked<0) return;
        settings.ImportedVillage=choices[picked].Imported;
        settings.LocalVillage=choices[picked].Local;
        Write(settings);
        Log("Selected: "+choices[picked].Label);
    }
    async Task BackupBeforeUpdate() {
        var database=VillageDatabase(Read());
        var backup=Path.Combine(state,"backups",Path.GetFileNameWithoutExtension(database)+"-before-"+ReleaseVersion+".sqlite3");
        if (!File.Exists(database) || File.Exists(backup)) return;
        await ToolQuiet("--db",database,"backup-db",backup);
        Log("Saved a pre-update copy of your village in Save Backups.");
    }
    async Task StartServer(Settings s) {
        if (backend is {HasExited:false}) return;
        var command=Command("--db",VillageDatabase(s),"serve","--launcher-stdin","--port",s.Port.ToString(),"--game-tables",s.GameTables,
                            "--xapk",s.Xapk,"--obb",s.Obb!,"--inventory",s.Inventory,
                            "--transport-key-file",Path.Combine(state,"private-client","transport-key.txt"));
        if (string.IsNullOrEmpty(s.ImportedVillage) && !string.IsNullOrEmpty(s.LocalVillage)) {
            command.ArgumentList.Add("--local-village-id");
            command.ArgumentList.Add(s.LocalVillage);
        }
        command.RedirectStandardInput=true;
        backend=Process.Start(command)
                ?? throw new IOException("Could not start the Village Life server");
        try { processJob.Add(backend); } catch { if(!backend.HasExited)backend.Kill(true);throw; }
        var process=backend;
        _=Task.Run(async()=>{while(await process.StandardOutput.ReadLineAsync() is string line)Log(line);});
        var startupError=new TaskCompletionSource<string>();
        _=Task.Run(async()=>{
            while(await process.StandardError.ReadLineAsync() is string line) {
                Log(line);
                if (line.Contains("[VL-", StringComparison.Ordinal)) startupError.TrySetResult(line.Trim());
            }
            startupError.TrySetResult("");
        });
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(12));
        while (!process.HasExited && !deadline.IsCancellationRequested) {
            try {
                using var response=await http.GetAsync("http://127.0.0.1:"+s.Port+"/health",deadline.Token);
                if (response.IsSuccessStatusCode && !process.HasExited) {
                    using var health=JsonDocument.Parse(await response.Content.ReadAsStringAsync(deadline.Token));
                    if (health.RootElement.ValueKind==JsonValueKind.Object &&
                        health.RootElement.TryGetProperty("pid",out var pid) &&
                        pid.ValueKind==JsonValueKind.Number &&
                        pid.TryGetInt32(out int owner) && owner==process.Id) return;
                }
            } catch (HttpRequestException) { }
              catch (JsonException) { }
              catch (OperationCanceledException) { break; }
            await Task.Delay(250);
        }
        await Stop();
        var error=await Task.WhenAny(startupError.Task,Task.Delay(1000))==startupError.Task
            ? await startupError.Task : "";
        throw new InvalidOperationException(error.Length>0 ? error :
            "[VL-SERVER-FAILED] The local server did not become ready. Check the log for details.");
    }
    async Task Stop() {
        StopGameMonitoring();
        var process=backend;
        if (process is null || process.HasExited) {SetStage(0,"Server is stopped. Click Play to resume.");return;}
        SetStage(0,"Stopping the local server…");
        try { process.StandardInput.Close(); }
        catch (IOException) { }
        using var deadline=new CancellationTokenSource(TimeSpan.FromSeconds(5));
        try { await process.WaitForExitAsync(deadline.Token); }
        catch (OperationCanceledException) {
            if (!process.HasExited) {
                try { process.Kill(true); }
                catch (InvalidOperationException) when (process.HasExited) { }
            }
            await process.WaitForExitAsync();
        }
        Log("Local server stopped. Completed actions were saved as you played.");
        SetStage(0,"Server stopped. Click Play to resume.");
    }
    async Task Connection() {
        if (backend is null || backend.HasExited) {
            SetStage(0,"Click Play to start the server before checking the connection.");
            return;
        }
        SetStage(25,"Checking the selected BlueStacks instance…");
        var check=await AdbState();
        if (check.Status!="ready") { SetStage(0,AdbMessage(check.Status)); return; }
        SetStage(65,"Checking the connection to the local server…");
        await ToolQuietWithin(45,"probe-guest-backend","--port",Read().Port.ToString());
        SetStage(100,"BlueStacks can reach the local server.");
    }
    Task OpenData(){Directory.CreateDirectory(state);Process.Start(new ProcessStartInfo(state){UseShellExecute=true});return Task.CompletedTask;}
    async Task Diagnostics(){
        SetStage(10,"Diagnostics: collecting guest network evidence…");
        await Tool("verify-network","--port",Read().Port.ToString());
        SetStage(60,"Diagnostics: creating the support report…");
        var reports=Path.Combine(state,"reports");Directory.CreateDirectory(reports);
        var report=Path.Combine(reports,"support-"+DateTime.UtcNow.ToString("yyyyMMddTHHmmssZ")+".zip");
        await Tool("--db",VillageDatabase(Read()),"export-support",report,
                   "--launcher-version",ReleaseVersion,
                   "--build-manifest",Path.Combine(root,"BUILD-MANIFEST.json"),
                   "--adb-check");
        SetStage(100,"Diagnostics complete — open Technical log for the report location.");
        Log("[VL-NETWORK-UNVERIFIED] Tests collect evidence only; they do not create or certify an isolation policy.");
    }
    Task Help() {
        MessageBox.Show(this,"Click Play to open your village or resume setup. First-time setup uses a dedicated BlueStacks 5 Pie 64-bit instance.\n\nUse Import 0.2.6 Save to copy an older village. Choose Village switches between saved villages.\n\nUse Advanced diagnostics to report gameplay issues.","Village Life Help");
        return Task.CompletedTask;
    }
}
