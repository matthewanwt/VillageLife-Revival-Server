using System.Diagnostics;
using System.Drawing;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Windows.Forms;

namespace VillageLife;
internal static class Program { [STAThread] static void Main() { ApplicationConfiguration.Initialize(); Application.Run(new VillageLifeWindow()); } }

public sealed class VillageLifeWindow : Form {
    const string ReleaseVersion = "0.2.88";
    sealed class Settings { public string GameTables { get; set; }=""; public string Xapk { get; set; }=""; public string Inventory { get; set; }=""; public string? Obb { get; set; } public int Port { get; set; }=80; public bool ClientPrepared { get; set; } public string ImportedVillage { get; set; }=""; }
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
    readonly Label stage=new(){Dock=DockStyle.Bottom,Height=25,Padding=new Padding(8,4,0,0),Text="Ready — choose Set Up Game on first use."};
    readonly ProgressBar progress=new(){Dock=DockStyle.Bottom,Height=16,Minimum=0,Maximum=100,Value=0};
    readonly HttpClient http=new(){Timeout=TimeSpan.FromSeconds(4)}; readonly List<Button> actions=new(); Process? backend; bool closing,busy;
    string ServerExe=>Path.Combine(root,"bin","VillageLifeServer","VillageLifeServer.exe"); string SettingsFile=>Path.Combine(state,"launcher-settings.json");
    string BundledGame=>Path.Combine(root,"game-assets","Village-Life-Original.xapk");
    string PrivateAssets=>Path.Combine(root,"private-assets");
    string SigningJdkHome=>Path.Combine(root,"signing-tools","jdk");
    public VillageLifeWindow() {
        Text="Village Life Community Test "+ReleaseVersion;Width=960;Height=660;MinimumSize=new(760,480);StartPosition=FormStartPosition.CenterScreen;Controls.Add(output);Controls.Add(stage);Controls.Add(progress);Controls.Add(bar);
        Add("Play / Restart",Play);Add("Stop",Stop);Add("Set Up Game",Setup);Add("Connection",Connection);Add("Save Backups",OpenData);Add("Logs",OpenData);Add("Help",Help);Add("Advanced diagnostics",Diagnostics);Add("Import 0.2.6 Save",ImportLegacy);Add("Choose Village",ChooseVillage);
        FormClosing+=async(_,e)=>{if(!closing&&backend is {HasExited:false}){e.Cancel=true;closing=true;await Stop();Close();}};
        Log("Village Life Community Test "+ReleaseVersion);Log("First use: click Set Up Game, select a dedicated Pie64 instance, then choose Play / Restart. The complete installer includes the game archive.");Log("Saves, prepared client files, and your local signing identity stay in Local AppData.");
        if(!File.Exists(ServerExe))Log("[VL-BUILD-INCOMPLETE] Bundled server missing: "+ServerExe);
    }
    void Add(string name,Func<Task> action){var b=new Button{Text=name,Width=150,Height=35,Margin=new Padding(4)};b.Click+=async(_,_)=>{if(busy){Log("Please wait for the current step to finish.");return;}busy=true;foreach(var item in actions)item.Enabled=false;try{await action();}catch(OperationCanceledException){SetStage(progress.Value,"Cancelled — choose an action when ready.");}catch(Exception e){SetStage(progress.Value,"Could not complete — see the message below.");Log("[VL-TOOL-FAILED] "+e.Message);}finally{busy=false;if(!IsDisposed)foreach(var item in actions)item.Enabled=true;}};actions.Add(b);bar.Controls.Add(b);}
    void Log(string value){if(IsDisposed)return;if(InvokeRequired){BeginInvoke(()=>Log(value));return;}output.AppendText(DateTime.Now.ToString("HH:mm:ss")+"  "+value+Environment.NewLine);}
    void SetStage(int value,string text){if(IsDisposed)return;if(InvokeRequired){BeginInvoke(()=>SetStage(value,text));return;}progress.Value=Math.Clamp(value,0,100);stage.Text=text;}
    Settings Read(){try{return JsonSerializer.Deserialize<Settings>(File.ReadAllText(SettingsFile))??new();}catch{return new();}}
    void Write(Settings s){Directory.CreateDirectory(state);var pending=SettingsFile+".pending";File.WriteAllText(pending,JsonSerializer.Serialize(s,new JsonSerializerOptions{WriteIndented=true}));File.Move(pending,SettingsFile,true);}
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
        using var dialog = new Form {Text=title, Width=690, Height=238, StartPosition=FormStartPosition.CenterParent,
            FormBorderStyle=FormBorderStyle.FixedDialog, MaximizeBox=false, MinimizeBox=false};
        var items = new ComboBox {Left=20, Top=91, Width=630, DropDownStyle=ComboBoxStyle.DropDownList};
        items.Items.AddRange(choices);
        items.SelectedIndex = initial;
        var select = new Button {Text="Continue", Left=447, Top=144, Width=99, DialogResult=DialogResult.OK};
        var cancel = new Button {Text="Cancel", Left=551, Top=144, Width=99, DialogResult=DialogResult.Cancel};
        dialog.Controls.AddRange(new Control[] {new Label {Text=detail, Left=20, Top=16, Width=630, Height=69},
                                                items, select, cancel});
        dialog.AcceptButton=select;
        dialog.CancelButton=cancel;
        return dialog.ShowDialog(this)==DialogResult.OK ? items.SelectedIndex : -1;
    }
    async Task ImportLegacy() {
        RequireStopped();
        using var picker = new FolderBrowserDialog {
            Description="Select the old 0.2.6 installation or its backend/private_state backup. Close its game and launcher first.",
            UseDescriptionForTitle=true, ShowNewFolderButton=false
        };
        if (picker.ShowDialog(this)!=DialogResult.OK) return;
        using var preview = await ReadVillageList("preview-legacy-villages",picker.SelectedPath);
        var candidates = preview.RootElement.GetProperty("villages").EnumerateArray().ToArray();
        int skipped = preview.RootElement.GetProperty("skipped").GetInt32();
        if (candidates.Length==0)
            throw new InvalidOperationException("No readable 0.2.6 save and profile pair was found. Select the folder containing the old Village Life.exe or its private_state backup.");
        string detail = "Choose a village to copy. Keep 0.2.6 and its BlueStacks instance closed, and use a separate Pie 64-bit instance for this launcher.";
        if (skipped>0) detail += $" Skipped {skipped} unreadable or unsupported save(s).";
        int chosen = PickVillage("Import 0.2.6 Save",detail,candidates.Select(VillageLabel).ToArray());
        if (chosen<0) return;
        var entry = candidates[chosen];
        var key = entry.GetProperty("key").GetString()!;
        await ToolQuiet("copy-legacy-village",picker.SelectedPath,key,entry.GetProperty("fingerprint").GetString()!);
        var settings = Read();
        settings.ImportedVillage=key;
        Write(settings);
        Log("Selected imported village: "+VillageLabel(entry));
        Log("Use Play / Restart on your separate BlueStacks instance, or Set Up Game if you have not prepared it.");
    }
    async Task ChooseVillage() {
        RequireStopped();
        using var list = await ReadVillageList("list-legacy-villages");
        var copies = list.RootElement.EnumerateArray().ToArray();
        var settings = Read();
        var keys = new[] {""}.Concat(copies.Select(row=>row.GetProperty("key").GetString()!)).ToArray();
        var choices = new[] {"Current village (created in the newer launcher)"}
            .Concat(copies.Select(row=>"Imported from 0.2.6 — "+VillageLabel(row))).ToArray();
        int picked = PickVillage("Choose Village","Select which village to open the next time you click Play / Restart.",
                                 choices,Math.Max(0,Array.IndexOf(keys,settings.ImportedVillage)));
        if (picked<0) return;
        settings.ImportedVillage=keys[picked];
        Write(settings);
        Log("Selected: "+choices[picked]);
    }
    async Task BackupBeforeUpdate() {
        var database=defaultDatabase;
        var backup=Path.Combine(state,"backups","worlds-before-"+ReleaseVersion+".sqlite3");
        if (!File.Exists(database) || File.Exists(backup)) return;
        await ToolQuiet("--db",database,"backup-db",backup);
        Log("Saved a pre-update copy of your village in Save Backups.");
    }
    async Task Setup(){RequireStopped();var s=Read();ChooseGameArchive(s);SetStage(5,"Setup: choosing your dedicated BlueStacks instance…");await BindInstance();
        if(MessageBox.Show(this,"Setup prepares your local XAPK for the selected BlueStacks instance. Replacing an app signed with a different key can erase its Android app data. Use a dedicated test instance and back up anything important.","Prepare Village Life",MessageBoxButtons.OKCancel,MessageBoxIcon.Warning)!=DialogResult.OK)return;await BackupBeforeUpdate();SetStage(12,"Setup: starting the selected BlueStacks instance and waiting for ADB…");await ToolQuiet("start-instance");await ToolQuiet("adb-check");
        var privateClient=Path.Combine(state,"private-client");SetStage(20,"Setup: preparing a private game copy (this can take a few minutes)…");await ToolQuiet("prepare-original-client","--xapk",s.Xapk,"--output",privateClient,"--java-home",SigningJdkHome,"--prepare-data");s.GameTables=Path.Combine(privateClient,"game_tables.sqlite");s.Inventory=Path.Combine(privateClient,"obb_tcf.inventory.csv");var apk=Path.Combine(privateClient,"client-local-signed.apk");s.Obb=Path.Combine(privateClient,"main.241.com.playdemic.villagelife.android.obb");if(!File.Exists(apk)||!File.Exists(s.Obb))throw new InvalidOperationException("[VL-CLIENT-PREPARE-FAILED] Prepared APK or extracted expansion file missing");SetStage(65,"Setup: checking the selected BlueStacks instance…");var installed=await Once(30,"check-original-game");if(installed.Item1!=0)throw new InvalidOperationException(installed.Item3.Trim());using var installedJson=JsonDocument.Parse(installed.Item2);if(installedJson.RootElement.GetProperty("installed").GetBoolean()&&MessageBox.Show(this,"Village Life is already installed in this selected instance. Replacing it removes the current Android app data. Cancel and back it up first if you need it.","Replace existing Village Life?",MessageBoxButtons.OKCancel,MessageBoxIcon.Warning)!=DialogResult.OK)return;SetStage(75,"Setup: installing Village Life into the selected instance…");await ToolQuiet("install-prepared-client","--apk",apk,"--obb",s.Obb,"--replace");s.ClientPrepared=true;Write(s);SetStage(100,"Setup complete — click Play / Restart to start Village Life.");Log("Setup complete.");}
    async Task BindInstance(){var r=await Once(30,"list-instances");if(r.Item1!=0)throw new InvalidOperationException(r.Item3.Trim());using var json=JsonDocument.Parse(r.Item2);var rows=json.RootElement.EnumerateArray().ToArray();if(rows.Length==0)throw new InvalidOperationException("[VL-BS-NO-PIE64] Create a dedicated Pie64 BlueStacks instance first.");using var d=new Form{Text="Choose dedicated Village Life instance",Width=650,Height=220,StartPosition=FormStartPosition.CenterParent};var c=new ComboBox{Left=20,Top=58,Width=590,DropDownStyle=ComboBoxStyle.DropDownList};foreach(var row in rows)c.Items.Add($"{row.GetProperty("display_name").GetString()} [{row.GetProperty("id").GetString()}] ADB {row.GetProperty("adb_port").GetInt32()}");c.SelectedIndex=0;d.Controls.AddRange(new Control[]{new Label{Text="Only the selected instance will be used; there is no default-instance fallback.",Left=20,Top=20,Width=590},c,new Button{Text="Bind this exact instance",Left=414,Top=112,Width=196,DialogResult=DialogResult.OK}});if(d.ShowDialog(this)!=DialogResult.OK)throw new OperationCanceledException();await ToolQuiet("bind-instance",rows[c.SelectedIndex].GetProperty("id").GetString()!);}
    async Task StartServer(Settings s) {
        if (backend is {HasExited:false}) return;
        var portCheck=new System.Net.Sockets.TcpListener(System.Net.IPAddress.Loopback,s.Port);
        try { portCheck.Start(); }
        catch (System.Net.Sockets.SocketException) {
            throw new InvalidOperationException("The Village Life server port is already in use. Close the old launcher and try again.");
        }
        finally { portCheck.Stop(); }
        backend=Process.Start(Command("--db",VillageDatabase(s),"serve","--port",s.Port.ToString(),"--game-tables",s.GameTables,
                                      "--xapk",s.Xapk,"--obb",s.Obb!,"--inventory",s.Inventory))
                ?? throw new IOException("Could not start the Village Life server");
        var process=backend;
        _=Task.Run(async()=>{while(await process.StandardOutput.ReadLineAsync() is string line)Log(line);});
        _=Task.Run(async()=>{while(await process.StandardError.ReadLineAsync() is string line)Log(line);});
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(12));
        while (!process.HasExited && !deadline.IsCancellationRequested) {
            try {
                using var response=await http.GetAsync("http://127.0.0.1:"+s.Port+"/health",deadline.Token);
                if (response.IsSuccessStatusCode && !process.HasExited) return;
            } catch (HttpRequestException) { }
              catch (OperationCanceledException) { break; }
            await Task.Delay(250);
        }
        await Stop();
        throw new InvalidOperationException("[VL-SERVER-FAILED] The local server did not become ready.");
    }
    async Task Play() {
        var settings = Read();
        if (!Ready(settings)) { Log("[VL-SETUP-REQUIRED] Run Set Up Game first."); return; }
        SetStage(10,"Starting: validating your selected BlueStacks instance…");
        await ToolQuiet("verify-instance");
        await BackupBeforeUpdate();
        SetStage(35,"Starting: waiting for BlueStacks…");
        await ToolQuiet("start-instance");
        await ToolQuiet("adb-check");
        await ToolQuietWithin(30,"stop-original-game");
        bool startNew = backend is null || backend.HasExited;
        try {
            await StartServer(settings);
            SetStage(70,"Starting: checking game-to-server connection…");
            await ToolQuiet("probe-guest-backend","--port",settings.Port.ToString());
            SetStage(90,"Starting Village Life…");
            await ToolQuietWithin(70,"launch-original-game");
        } catch {
            if (startNew && backend is {HasExited:false}) await Stop();
            throw;
        }
        SetStage(100,"Village Life started — use the BlueStacks window to play.");
        Log("Village Life launch requested. Network isolation has not been certified; see Advanced diagnostics for technical evidence.");
    }
    async Task Stop(){var p=backend;if(p is null||p.HasExited){Log("Backend is not running");return;}p.Kill(true);await p.WaitForExitAsync();Log("New backend stopped; saves remain in Local AppData.");}
    async Task Connection(){var s=Read();if(!Ready(s)){Log("[VL-SETUP-REQUIRED] Run Set Up Game first.");return;}await Tool("adb-check");await Tool("probe-guest-backend","--port",s.Port.ToString());}
    Task OpenData(){Directory.CreateDirectory(state);Process.Start(new ProcessStartInfo(state){UseShellExecute=true});return Task.CompletedTask;}
    async Task Diagnostics(){SetStage(10,"Diagnostics: collecting guest network evidence…");await Tool("verify-network","--port",Read().Port.ToString());SetStage(75,"Diagnostics: exporting safe missing-request summary…");await Tool("--db",VillageDatabase(Read()),"export-missing-requests");SetStage(100,"Diagnostics complete — review the technical log above.");Log("[VL-NETWORK-UNVERIFIED] Tests collect evidence only; they do not create or certify an isolation policy.");}
    Task Help() {
        MessageBox.Show(this,"First-time setup requires BlueStacks 5 and a dedicated Pie64 instance. Set Up Game prepares the bundled game archive locally. If your current reliability-test setup already works, use Play / Restart to open your existing village.\n\nUse Import 0.2.6 Save to copy an older village, then Choose Village to switch between it and your current village. Keep the old installation and use a separate BlueStacks instance.\n\nUse Advanced diagnostics to report gameplay issues. Saves, backups and your local signing identity stay in Local AppData.","Village Life Community Test");
        return Task.CompletedTask;
    }
}
