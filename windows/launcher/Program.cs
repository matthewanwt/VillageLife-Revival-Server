using System.Diagnostics;
using System.Drawing;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Windows.Forms;

namespace VillageLife;
internal static class Program { [STAThread] static void Main() { ApplicationConfiguration.Initialize(); Application.Run(new VillageLifeWindow()); } }

public sealed partial class VillageLifeWindow : Form {
    const string ReleaseVersion = "0.3.2";
    const string ReleaseTitle = "Village Life Community Update " + ReleaseVersion;
    sealed class Settings { public string GameTables { get; set; }=""; public string Xapk { get; set; }=""; public string Inventory { get; set; }=""; public string? Obb { get; set; } public int Port { get; set; }=80; public bool ClientPrepared { get; set; } public bool PreparedFilesReady { get; set; } public bool VillageChoiceMade { get; set; } public string ImportedVillage { get; set; }=""; }
    readonly string root=Directory.GetParent(AppContext.BaseDirectory.TrimEnd(Path.DirectorySeparatorChar))?.FullName??AppContext.BaseDirectory;
    static string DefaultDatabase() {
        var alternate = Environment.GetEnvironmentVariable("VILLAGELIFE_DB");
        return string.IsNullOrWhiteSpace(alternate)
            ? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),"VillageLifeRevivalNext","worlds.sqlite3")
            : Path.GetFullPath(alternate);
    }
    readonly string defaultDatabase=DefaultDatabase();
    string state=>Path.GetDirectoryName(defaultDatabase)!;
    readonly TextBox output=new(){Multiline=true,ReadOnly=true,ScrollBars=ScrollBars.Vertical,Dock=DockStyle.Fill,Font=new Font("Consolas",10),WordWrap=false};
    readonly FlowLayoutPanel bar=new(){Dock=DockStyle.Top,Height=132,AutoScroll=true,WrapContents=true,Padding=new Padding(6)};
    readonly Label stage=new(){Dock=DockStyle.Bottom,Height=25,Padding=new Padding(8,4,0,0),Text="Click Play to start or resume setup."};
    readonly ProgressBar progress=new(){Dock=DockStyle.Bottom,Height=16,Minimum=0,Maximum=100,Value=0};
    readonly HttpClient http=new(){Timeout=TimeSpan.FromSeconds(4)}; readonly List<Button> actions=new(); Process? backend; bool closing,busy;
    string ServerExe=>Path.Combine(root,"bin","VillageLifeServer","VillageLifeServer.exe"); string SettingsFile=>Path.Combine(state,"launcher-settings.json");
    string BundledGame=>Path.Combine(root,"game-assets","Village-Life-Original.xapk");
    string PrivateAssets=>Path.Combine(root,"private-assets");
    string SigningJdkHome=>Path.Combine(root,"signing-tools","jdk");
    public VillageLifeWindow() {
        Text=ReleaseTitle;Width=960;Height=660;MinimumSize=new(760,480);StartPosition=FormStartPosition.CenterScreen;
        Icon=Icon.ExtractAssociatedIcon(Application.ExecutablePath);
        Controls.Add(output);Controls.Add(stage);Controls.Add(progress);Controls.Add(bar);
        Add("Play",Play);Add("Stop",Stop);Add("Set Up Game",Setup);Add("Connection",Connection);Add("Save Backups",OpenData);Add("Logs",OpenData);Add("Help",Help);Add("Advanced diagnostics",Diagnostics);Add("Import 0.2.6 Save",async()=>{await ImportLegacy();});Add("Choose Village",ChooseVillage);Add("Add Gems",AddGems);
        FormClosing+=async(_,e)=>{
            if (closing || backend is not {HasExited:false}) return;
            closing=true;
            if (e.CloseReason==CloseReason.WindowsShutDown) return;
            e.Cancel=true;
            try { await Stop(); }
            finally { Close(); }
        };
        gameMonitor.Tick+=CheckGameClosed;
        FormClosed+=(_,_)=>gameMonitor.Dispose();
        Log(ReleaseTitle);Log("Click Play. Village Life will guide you through any steps still needed.");
        if(!File.Exists(ServerExe))Log("[VL-BUILD-INCOMPLETE] Bundled server missing: "+ServerExe);
    }
    void Add(string name,Func<Task> action){var b=new Button{Text=name,Width=150,Height=35,Margin=new Padding(4)};b.Click+=async(_,_)=>{if(busy){Log("Please wait for the current step to finish.");return;}busy=true;foreach(var item in actions)item.Enabled=false;try{await action();}catch(OperationCanceledException){SetStage(progress.Value,"Cancelled — choose an action when ready.");}catch(Exception e){SetStage(progress.Value,"Could not complete — see the message below.");Log("[VL-TOOL-FAILED] "+e.Message);}finally{busy=false;if(!IsDisposed)foreach(var item in actions)item.Enabled=true;}};actions.Add(b);bar.Controls.Add(b);}
    void Log(string value){if(IsDisposed)return;if(InvokeRequired){BeginInvoke(()=>Log(value));return;}output.AppendText(DateTime.Now.ToString("HH:mm:ss")+"  "+value+Environment.NewLine);}
    void SetStage(int value,string text){if(IsDisposed)return;if(InvokeRequired){BeginInvoke(()=>SetStage(value,text));return;}progress.Value=Math.Clamp(value,0,100);stage.Text=text;}
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
    ProcessStartInfo Command(params string[] args){if(!File.Exists(ServerExe))throw new FileNotFoundException("Bundled new backend missing",ServerExe);var p=new ProcessStartInfo(ServerExe){WorkingDirectory=root,UseShellExecute=false,RedirectStandardOutput=true,RedirectStandardError=true,CreateNoWindow=true,StandardOutputEncoding=Encoding.UTF8,StandardErrorEncoding=Encoding.UTF8};foreach(var a in args)p.ArgumentList.Add(a);p.Environment["PYTHONUTF8"]="1";return p;}
    async Task<(int,string,string)> Once(int seconds,params string[] args){using var p=Process.Start(Command(args))??throw new IOException("Could not start backend tool");var o=p.StandardOutput.ReadToEndAsync();var e=p.StandardError.ReadToEndAsync();using var deadline=new CancellationTokenSource(TimeSpan.FromSeconds(seconds));try{await p.WaitForExitAsync(deadline.Token);}catch(OperationCanceledException){p.Kill(true);throw new TimeoutException("[VL-TOOL-TIMEOUT]");}return(p.ExitCode,await o,await e);}
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
        Write(settings);
        Log("Selected imported village: "+VillageLabel(entry));
        return true;
    }
    async Task ChooseVillage() {
        RequireStopped();
        using var list = await ReadVillageList("list-legacy-villages");
        var copies = list.RootElement.EnumerateArray().ToArray();
        var settings = Read();
        var keys = new[] {""}.Concat(copies.Select(row=>row.GetProperty("key").GetString()!)).ToArray();
        var choices = new[] {"Current village (created in the newer launcher)"}
            .Concat(copies.Select(row=>"Imported from 0.2.6 — "+VillageLabel(row))).ToArray();
        int picked = PickVillage("Choose Village","Select which village to open the next time you click Play.",
                                 choices,Math.Max(0,Array.IndexOf(keys,settings.ImportedVillage)));
        if (picked<0) return;
        settings.ImportedVillage=keys[picked];
        Write(settings);
        Log("Selected: "+choices[picked]);
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
                            "--xapk",s.Xapk,"--obb",s.Obb!,"--inventory",s.Inventory);
        command.RedirectStandardInput=true;
        backend=Process.Start(command)
                ?? throw new IOException("Could not start the Village Life server");
        var process=backend;
        _=Task.Run(async()=>{while(await process.StandardOutput.ReadLineAsync() is string line)Log(line);});
        var startupError=new TaskCompletionSource<string>();
        _=Task.Run(async()=>{
            while(await process.StandardError.ReadLineAsync() is string line) {
                Log(line);
                if (IsCode(line,"VL-SERVER-PORT-IN-USE")) startupError.TrySetResult(line);
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
    async Task Diagnostics(){SetStage(10,"Diagnostics: collecting guest network evidence…");await Tool("verify-network","--port",Read().Port.ToString());SetStage(75,"Diagnostics: exporting safe missing-request summary…");await Tool("--db",VillageDatabase(Read()),"export-missing-requests");SetStage(100,"Diagnostics complete — review the technical log above.");Log("[VL-NETWORK-UNVERIFIED] Tests collect evidence only; they do not create or certify an isolation policy.");}
    Task Help() {
        MessageBox.Show(this,"Click Play to open your village or resume setup. First-time setup uses a dedicated BlueStacks 5 Pie 64-bit instance.\n\nUse Import 0.2.6 Save to copy an older village. Choose Village switches between saved villages.\n\nUse Advanced diagnostics to report gameplay issues.","Village Life Help");
        return Task.CompletedTask;
    }
}
