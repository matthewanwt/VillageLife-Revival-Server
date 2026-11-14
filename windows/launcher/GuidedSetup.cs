using System.Diagnostics;
using System.Drawing;
using System.Text.Json;
using System.Windows.Forms;

namespace VillageLife;

public sealed partial class VillageLifeWindow {
    const string AdbHelp = "https://support.bluestacks.com/hc/en-us/articles/23925869130381";
    const string PieHelp = "https://support.bluestacks.com/hc/en-us/articles/4406032772877";
    const string BlueStacksDownload = "https://www.bluestacks.com/download.html";

    static void OpenGuide(string url) =>
        Process.Start(new ProcessStartInfo(url) { UseShellExecute=true });

    static bool IsCode(string message, params string[] codes) =>
        codes.Any(code=>message.StartsWith("["+code+"]",StringComparison.Ordinal));

    async Task<string> ReadTool(int seconds, params string[] args) {
        var (exit, output, error) = await Once(seconds,args);
        if (exit!=0)
            throw new InvalidOperationException(string.IsNullOrWhiteSpace(error) ? "[VL-TOOL-ERROR] Tool failed" : error.Trim());
        return output;
    }

    async Task FollowGuide(string title, string instructions, string initialStatus,
                           string actionLabel, Func<Task> action,
                           Func<Task<(bool Ready,string Status)>> check,
                           string? helpUrl=null) {
        using var guide = new Form {
            Text=title, StartPosition=FormStartPosition.Manual,
            FormBorderStyle=FormBorderStyle.FixedDialog, MaximizeBox=false, MinimizeBox=false,
            ShowInTaskbar=false, TopMost=true, AutoScaleMode=AutoScaleMode.Font,
            AutoSize=true, AutoSizeMode=AutoSizeMode.GrowAndShrink
        };
        var layout=SetupDialogLayout(530);
        var status=SetupText(initialStatus,530);
        var open=SetupButton(actionLabel);
        var help=SetupButton("Show screenshots");
        help.Visible=helpUrl!=null;
        var cancel=SetupButton("Close setup",DialogResult.Cancel);
        layout.Controls.Add(SetupText(instructions,530));
        layout.Controls.Add(status);
        layout.Controls.Add(SetupButtons(cancel,help,open));
        guide.Controls.Add(layout);
        guide.CancelButton=cancel;
        using var timer=new System.Windows.Forms.Timer { Interval=2500 };
        Task pending=Task.CompletedTask;
        bool acting=false;

        async Task Check() {
            try {
                var result=await check();
                if (!guide.Visible) return;
                status.Text=result.Status;
                if (result.Ready) guide.DialogResult=DialogResult.OK;
            } catch (Exception e) {
                if (guide.Visible) status.Text="Couldn’t check this step yet. "+e.Message;
            }
        }
        timer.Tick+=(_,_)=>{if (!acting && pending.IsCompleted) pending=Check();};
        open.Click+=async(_,_)=>{
            acting=true;
            open.Enabled=false;
            try { await action(); }
            catch (Exception e) { if (guide.Visible) status.Text=e.Message; }
            finally { acting=false; if (guide.Visible) open.Enabled=true; }
        };
        help.Click+=(_,_)=>{
            try { OpenGuide(helpUrl!); }
            catch (Exception e) { status.Text=e.Message; }
        };
        guide.Shown+=(_,_)=>{
            var area=Screen.FromControl(this).WorkingArea;
            guide.Location=new Point(Math.Max(area.Left,area.Right-guide.Width-24),area.Top+36);
            timer.Start();
        };
        var result=guide.ShowDialog(this);
        timer.Stop();
        await pending;
        if (result!=DialogResult.OK) throw new OperationCanceledException();
    }

    async Task EnsureBlueStacks() {
        var result=await Once(15,"check-bluestacks");
        if (result.Item1==0) return;
        if (!IsCode(result.Item3.Trim(),"VL-BS-NOT-FOUND"))
            throw new InvalidOperationException(result.Item3.Trim());
        await FollowGuide("Install BlueStacks 5",
            "Open the official BlueStacks download page and install BlueStacks 5. When it has finished, open BlueStacks once. Village Life will continue when it finds the installation.",
            "Waiting for BlueStacks 5…","Open download page",
            ()=>{OpenGuide(BlueStacksDownload); return Task.CompletedTask;},
            async()=>((await Once(15,"check-bluestacks")).Item1==0,"Waiting for BlueStacks 5…"));
    }

    async Task<JsonElement[]> AvailableInstances() {
        var (exit, output, error)=await Once(20,"list-instances","--eligible");
        if (exit!=0) {
            if (IsCode(error.Trim(),"VL-BS-CONFIG-MISSING")) return [];
            throw new InvalidOperationException(error.Trim());
        }
        using var list=JsonDocument.Parse(output);
        return list.RootElement.EnumerateArray().Select(row=>row.Clone()).ToArray();
    }

    async Task EnsureInstance(bool chooseAgain) {
        await EnsureBlueStacks();
        if (!chooseAgain) {
            var result=await Once(20,"verify-instance","--selection-only");
            if (result.Item1==0) return;
            if (!IsCode(result.Item3.Trim(),"VL-BS-INSTANCE-UNSET","VL-BS-INSTANCE-MISSING","VL-BS-INSTANCE-CHANGED",
                        "VL-BS-INSTANCE-RENAMED","VL-BS-BINDING-INVALID","VL-BS-PORT-DIVERGED","VL-BS-CONFIG-MISSING",
                        "VL-LEGACY-INSTANCE-PROTECTED"))
                throw new InvalidOperationException(result.Item3.Trim());
            Log(result.Item3.Trim());
        }
        RequireStopped();
        var rows=await AvailableInstances();
        JsonElement row;
        while (true) {
            if (rows.Length>0) {
                var choices=rows.Select(item=>$"{item.GetProperty("display_name").GetString()} [{item.GetProperty("id").GetString()}]")
                                .Append("Create a new Pie 64-bit instance").ToArray();
                int selected=PickVillage("Choose your BlueStacks instance",
                    "Choose an existing instance dedicated to this version, or create a new one. Keep any 0.2.6 instance separate.",
                    choices,-1);
                if (selected<0) throw new OperationCanceledException();
                if (selected<rows.Length) { row=rows[selected]; break; }
            }
            var known=rows.Select(item=>item.GetProperty("id").GetString()).ToHashSet();
            SetStage(10,"Create a Pie 64-bit instance in BlueStacks.");
            await ToolQuiet("open-instance-manager");
            await FollowGuide("Create your Village Life instance",
                "In Multi-instance Manager, choose Instance → Fresh instance → Pie 64-bit → Next. Complete the creation and download. You can give the instance any name.",
                "Waiting for a Pie 64-bit instance…","Open instance manager",
                ()=>ToolQuiet("open-instance-manager"),
                async()=>{
                    rows=await AvailableInstances();
                    return (rows.Any(item=>!known.Contains(item.GetProperty("id").GetString())),
                            "Waiting for a new Pie 64-bit instance…");
                },PieHelp);
        }
        var settings=Read();
        var id=row.GetProperty("id").GetString()!;
        var binding=Path.Combine(state,"bluestacks-binding.json");
        string? previous=null;
        if (File.Exists(binding)) {
            try {
                using var receipt=JsonDocument.Parse(File.ReadAllText(binding));
                if (receipt.RootElement.TryGetProperty("id",out var entry) && entry.ValueKind==JsonValueKind.String)
                    previous=entry.GetString();
            } catch (JsonException) { }
        }
        if (previous!=id && settings.ClientPrepared) {
            settings.ClientPrepared=false;
            Write(settings);
        }
        await ToolQuiet("bind-instance",id);
    }

    async Task<(string Name,string Status)> AdbState() {
        using var json=JsonDocument.Parse(await ReadTool(23,"adb-check","--once"));
        return (json.RootElement.GetProperty("name").GetString()!,
                json.RootElement.GetProperty("status").GetString()!);
    }

    async Task EnsureAndroid() {
        SetStage(20,"Opening your selected BlueStacks instance…");
        await ToolQuiet("start-instance");
        var check=await AdbState();
        if (check.Status=="ready") return;
        SetStage(30,"Waiting for Android and Android Debug Bridge…");
        await FollowGuide("Connect to "+check.Name,
            $"In the BlueStacks window for {check.Name}, click the gear on the side toolbar (or Menu → Settings).\n\nChoose Advanced → Android Debug Bridge, turn it on, then click Save changes. If BlueStacks asks to restart, let it finish.",
            AdbMessage(check.Status),"Open selected BlueStacks",()=>ToolQuiet("start-instance"),
            async()=>{var next=await AdbState(); return (next.Status=="ready",AdbMessage(next.Status));},AdbHelp);
        Log("BlueStacks connected and Android finished starting.");
    }

    static string AdbMessage(string status) => status switch {
        "ready"=>"Connected. Android is ready.",
        "booting"=>"Connected. Waiting for Android to finish starting…",
        "initializing"=>"Waiting for BlueStacks to finish starting this instance. Finish any first-run prompts in its window. If it is already open, close that instance and use Open selected BlueStacks to retry.",
        "tool_unavailable"=>"The BlueStacks connection tool did not respond. Check that BlueStacks is running.",
        _=>"Waiting for the selected instance. If it has finished starting, check the Android Debug Bridge switch above."
    };

    async Task OfferVillageChoice() {
        var settings=Read();
        if (settings.ClientPrepared || settings.VillageChoiceMade || File.Exists(defaultDatabase) ||
            !string.IsNullOrEmpty(settings.ImportedVillage)) return;
        var choice=PickVillage("Choose your village","Start a fresh village or copy your existing 0.2.6 village.",
                               ["Start a new village","Copy my 0.2.6 village"],-1);
        if (choice<0 || (choice==1 && !await ImportLegacy())) throw new OperationCanceledException();
        settings=Read();
        settings.VillageChoiceMade=true;
        Write(settings);
    }

    async Task<bool> GameInstalled(params string[] options) {
        using var status=JsonDocument.Parse(await ReadTool(60,["check-original-game",..options]));
        return status.RootElement.GetProperty("installed").GetBoolean();
    }

    async Task<Settings> EnsureGame(Settings settings) {
        SetStage(44,"Checking the game and expansion file in BlueStacks…");
        if (Ready(settings) && await GameInstalled("--prepared","--obb",settings.Obb!)) return settings;
        RequireStopped();
        if (!File.Exists(settings.Xapk)) ChooseGameArchive(settings);
        var privateClient=Path.Combine(state,"private-client");
        var apk=Path.Combine(privateClient,"client-local-signed.apk");
        if ((!settings.ClientPrepared && !settings.PreparedFilesReady) || !File.Exists(apk) || !PreparedAssetsExist(settings)) {
            SetStage(49,"Preparing the bundled game files. This can take a few minutes…");
            await ToolQuiet("prepare-original-client","--xapk",settings.Xapk,"--output",privateClient,
                            "--java-home",SigningJdkHome,"--prepare-data");
            settings.GameTables=Path.Combine(privateClient,"game_tables.sqlite");
            settings.Inventory=Path.Combine(privateClient,"obb_tcf.inventory.csv");
            settings.Obb=Path.Combine(privateClient,"main.241.com.playdemic.villagelife.android.obb");
            if (!File.Exists(apk) || !PreparedAssetsExist(settings))
                throw new InvalidOperationException("The prepared game files are incomplete. Click Play to retry.");
            settings.PreparedFilesReady=true;
            Write(settings);
        }
        bool sameApk=await GameInstalled("--apk",apk);
        bool replace=!sameApk && await GameInstalled();
        if (replace && MessageBox.Show(this,
                "The selected BlueStacks instance already has Village Life. If its signing key differs, replacing it erases that app’s Android data. Cancel if this is your 0.2.6 instance or contains an app save you still need.",
                "Prepare this instance?",MessageBoxButtons.OKCancel,MessageBoxIcon.Warning,
                MessageBoxDefaultButton.Button2)!=DialogResult.OK) throw new OperationCanceledException();
        SetStage(61,sameApk ? "Completing the Village Life expansion transfer…" :
            "Installing Village Life and its expansion in the selected instance…");
        string[] args=[sameApk ? "repair-prepared-obb" : "install-prepared-client","--apk",apk,"--obb",settings.Obb!];
        await ToolQuietWithin(660,replace ? [..args,"--replace"] : args);
        if (!await GameInstalled("--prepared","--obb",settings.Obb!))
            throw new InvalidOperationException("BlueStacks did not confirm the game and expansion. Click Play to retry.");
        settings.ClientPrepared=true;
        Write(settings);
        return settings;
    }

    static bool PreparedAssetsExist(Settings settings) =>
        File.Exists(settings.GameTables) && File.Exists(settings.Inventory) && File.Exists(settings.Obb);

    async Task Setup() {
        RequireStopped();
        await GuidedPlay(chooseAgain:true);
    }

    Task Play()=>GuidedPlay(chooseAgain:false);

    async Task GuidedPlay(bool chooseAgain) {
        await OfferVillageChoice();
        SetStage(8,"Checking your dedicated BlueStacks instance…");
        await EnsureInstance(chooseAgain);
        await EnsureAndroid();
        await BackupBeforeUpdate();
        var settings=await EnsureGame(Read());
        StopGameMonitoring();
        try {
            await StartServer(settings);
            SetStage(75,"Checking whether BlueStacks can reach the local game server…");
            string? lastProbeError=null;
            try {
                await ToolQuietWithin(55,"probe-guest-backend","--port",settings.Port.ToString());
            } catch (InvalidOperationException e) when (IsCode(e.Message,"VL-GUEST-BACKEND-UNREACHABLE")) {
                lastProbeError=e.Message;
                Log(lastProbeError);
                await FollowGuide("Connect BlueStacks to the game server",
                    "The local server is running and Android Debug Bridge is connected. BlueStacks still can’t reach the game server. In your selected BlueStacks window, close the player and use Reopen BlueStacks below. This check retries automatically.",
                    "Waiting for the BlueStacks connection to the local server…","Reopen BlueStacks",
                    ()=>ToolQuiet("start-instance"),async()=>{
                        var result=await Once(55,"probe-guest-backend","--port",settings.Port.ToString());
                        var error=result.Item3.Trim();
                        if (result.Item1!=0 && error.Length>0 && error!=lastProbeError) {
                            Log(error);
                            lastProbeError=error;
                        }
                        return (result.Item1==0,"Waiting for the BlueStacks connection to the local server…");
                    });
            } catch (InvalidOperationException e) when (IsCode(e.Message,"VL-GUEST-PROBE-UNAVAILABLE")) {
                Log(e.Message+"; checking the game’s actual sign-in instead.");
            }
            await ToolQuietWithin(40,"stop-original-game");
            int baseline=await GameLogins(settings.Port);
            SetStage(90,"Opening Village Life and waiting for it to sign in…");
            await ToolQuietWithin(70,"launch-original-game");
            if (!await WaitForGameLogin(settings.Port,baseline))
                throw new InvalidOperationException("Village Life opened but hasn’t signed in to the local server. Click Play to retry, or use Advanced diagnostics if this keeps happening.");
            SetStage(100,"Village Life connected. Play in the BlueStacks window.");
            Log("Village Life signed in to the local server.");
            StartGameMonitoring(backend!);
        } catch {
            if (backend is {HasExited:false}) await Stop();
            throw;
        }
    }

    async Task<int> GameLogins(int port) {
        using var reply=await http.GetAsync("http://127.0.0.1:"+port+"/health");
        reply.EnsureSuccessStatusCode();
        using var health=JsonDocument.Parse(await reply.Content.ReadAsStringAsync());
        return health.RootElement.GetProperty("originalClientLogins").GetInt32();
    }

    async Task<bool> WaitForGameLogin(int port,int baseline) {
        var elapsed=Stopwatch.StartNew();
        while (backend is {HasExited:false} && elapsed.Elapsed<TimeSpan.FromSeconds(60)) {
            try { if (await GameLogins(port)>baseline) return true; }
            catch (HttpRequestException) { }
            catch (TaskCanceledException) { }
            await Task.Delay(1000);
        }
        return false;
    }
}
