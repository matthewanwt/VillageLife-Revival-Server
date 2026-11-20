using System.Diagnostics;
using System.Drawing;
using System.Text.Json;
using System.Windows.Forms;

namespace VillageLife;

public sealed partial class VillageLifeWindow {
    readonly Panel pageHost=new(){Dock=DockStyle.Fill,AccessibleName="Launcher pages"};
    readonly Dictionary<string,Panel> pages=new();
    readonly Dictionary<string,Button> navigation=new();
    readonly Font selectedNavigationFont=new("Segoe UI",9.5F,FontStyle.Bold);
    readonly Label pageTitle=new(){AutoSize=true,Font=new Font("Segoe UI",18,FontStyle.Bold)};
    readonly Label homeVillage=Body("Village linked to your selected BlueStacks instance");
    readonly Label homeInstance=Body("No BlueStacks instance selected yet");
    readonly Label homeStatus=Body("Click Play. We will guide you through any steps still needed.");
    readonly Label saveStatus=Body("Save information has not been loaded yet.");
    readonly Label backupStatus=Body("No backup information loaded yet.");
    readonly Label elapsedStatus=new(){AutoSize=true};
    readonly Label[] checklist=Enumerable.Range(0,4).Select(_=>Body("")).ToArray();
    readonly ListBox villages=new(){Dock=DockStyle.Top,Height=160,HorizontalScrollbar=true,IntegralHeight=false,AccessibleName="Saved villages"};
    readonly List<(string Label,string Imported,string Local)> villageChoices=new();
    readonly ListBox backups=new(){Dock=DockStyle.Top,Height=160,HorizontalScrollbar=true,IntegralHeight=false,AccessibleName="Recovery backups"};
    readonly TableLayoutPanel notice=new(){AutoSize=true,Dock=DockStyle.Top,ColumnCount=1,Padding=new Padding(12),Visible=false,BackColor=SystemColors.Info,ForeColor=SystemColors.InfoText,AccessibleName="Action required"};
    readonly Label noticeText=Body("");
    readonly Button retry=new(){Text="Retry",AutoSize=true,MinimumSize=new Size(90,34)};
    readonly System.Windows.Forms.Timer dashboardClock=new(){Interval=1000};
    readonly Stopwatch actionElapsed=new();
    Func<Task>? retryAction;
    string retryName="",currentPage="Play",currentAction="";
    int checklistPosition=-1;
    bool checklistRunning;

    static Label Body(string text)=>new(){Text=text,AutoSize=true,Margin=new Padding(0,3,0,8),Tag="wrap",UseMnemonic=false};
    static Label Heading(string text)=>new(){Text=text,AutoSize=true,Font=new Font("Segoe UI",11,FontStyle.Bold),Margin=new Padding(0,0,0,8),Tag="wrap"};
    static FlowLayoutPanel Row(params Control[] controls) {
        var row=new FlowLayoutPanel{Dock=DockStyle.Top,AutoSize=true,AutoSizeMode=AutoSizeMode.GrowAndShrink,WrapContents=true,Margin=new Padding(0,3,0,8)};
        row.Controls.AddRange(controls);return row;
    }
    static TableLayoutPanel Card(params Control[] controls) {
        var card=new TableLayoutPanel{Dock=DockStyle.Top,AutoSize=true,AutoSizeMode=AutoSizeMode.GrowAndShrink,ColumnCount=1,Padding=new Padding(16),Margin=new Padding(0,0,0,14),BorderStyle=BorderStyle.FixedSingle,AccessibleName=controls.FirstOrDefault()?.Text??"Section"};
        card.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));
        foreach(var control in controls)card.Controls.Add(control);
        card.SizeChanged+=(_,_)=>WrapText(card);
        return card;
    }
    static void WrapText(Control container) {
        foreach(Control control in container.Controls) {
            if(control is Label && Equals(control.Tag,"wrap"))control.MaximumSize=new Size(Math.Max(100,container.ClientSize.Width-container.Padding.Horizontal-12),0);
        }
    }
    Button ActionButton(string name,Func<Task> action,bool primary=false) {
        var button=new Button{Text=name,AutoSize=true,MinimumSize=new Size(primary?150:110,primary?44:36),Padding=new Padding(10,4,10,4),Margin=new Padding(0,0,8,4),UseVisualStyleBackColor=true};
        if(primary)button.Font=new Font(Font,FontStyle.Bold);
        button.Click+=async(_,_)=>await RunAction(name,action);
        actions.Add(button);return button;
    }
    TableLayoutPanel Page(string name,string description) {
        var scroll=new Panel{Dock=DockStyle.Fill,AutoScroll=true,Padding=new Padding(20,12,20,12),Visible=false,AccessibleName=name+" content"};
        var content=new TableLayoutPanel{Dock=DockStyle.Top,AutoSize=true,ColumnCount=1,AccessibleName=name+" sections"};
        content.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));
        content.Controls.Add(Body(description));
        content.SizeChanged+=(_,_)=>WrapText(content);
        scroll.Controls.Add(content);pageHost.Controls.Add(scroll);pages.Add(name,scroll);return content;
    }
    void BuildDashboard() {
        Text=ReleaseTitle;Font=new Font("Segoe UI",9.5F);AutoScaleMode=AutoScaleMode.Dpi;
        ClientSize=new Size(1000,Math.Min(780,Screen.FromControl(this).WorkingArea.Height-100));MinimumSize=new Size(820,640);StartPosition=FormStartPosition.CenterScreen;
        Icon=Icon.ExtractAssociatedIcon(Application.ExecutablePath);BackColor=SystemColors.Window;ForeColor=SystemColors.WindowText;
        var shell=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=2,RowCount=3};
        shell.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,174));shell.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));
        shell.RowStyles.Add(new RowStyle(SizeType.Absolute,82));shell.RowStyles.Add(new RowStyle(SizeType.Percent,100));shell.RowStyles.Add(new RowStyle(SizeType.Absolute,76));
        var brand=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=2,Padding=new Padding(18,14,12,8)};
        brand.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute,54));brand.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));
        brand.Controls.Add(new PictureBox{Image=Icon?.ToBitmap(),SizeMode=PictureBoxSizeMode.Zoom,Width=40,Height=40,AccessibleName="Village Life"});
        brand.Controls.Add(new Label{Text="Village Life",AutoSize=true,Font=new Font("Segoe UI",17,FontStyle.Bold),Anchor=AnchorStyles.Left});
        shell.Controls.Add(brand,0,0);shell.SetColumnSpan(brand,2);
        var sidebar=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=1,Padding=new Padding(10,12,8,10),BackColor=SystemColors.Control,AccessibleName="Navigation"};
        foreach(var name in new[]{"Play","My Villages","Backups","Help","Settings"}) {
            var nav=new Button{Text=name,TextAlign=ContentAlignment.MiddleLeft,Dock=DockStyle.Top,Height=44,FlatStyle=FlatStyle.Flat,Padding=new Padding(8,0,0,0),Margin=new Padding(0,0,0,5),AccessibleName=name+" page"};
            nav.FlatAppearance.BorderSize=0;nav.Click+=(_,_)=>ShowPage(name);navigation.Add(name,nav);sidebar.Controls.Add(nav);
        }
        sidebar.Controls.Add(new Label{Text="Community launcher\n"+ReleaseVersion,AutoSize=true,Margin=new Padding(10,24,0,0)});
        sidebar.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        shell.Controls.Add(sidebar,0,1);
        var main=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=1,RowCount=3,AccessibleName="Current page"};
        main.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));
        main.RowStyles.Add(new RowStyle(SizeType.AutoSize));main.RowStyles.Add(new RowStyle(SizeType.AutoSize));main.RowStyles.Add(new RowStyle(SizeType.Percent,100));
        pageTitle.Margin=new Padding(20,8,20,8);main.Controls.Add(pageTitle,0,0);
        notice.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));notice.Margin=new Padding(20,0,20,4);notice.Controls.Add(noticeText);
        var details=new Button{Text="Technical log",AutoSize=true,MinimumSize=new Size(110,34)};details.Click+=(_,_)=>ShowTechnicalLog();
        var instructions=new Button{Text="Help",AutoSize=true,MinimumSize=new Size(80,34)};instructions.Click+=(_,_)=>ShowPage("Help");
        retry.Click+=async(_,_)=>{if(retryAction is { } action)await RunAction(retryName,action);};
        notice.Controls.Add(Row(retry,instructions,details));notice.SizeChanged+=(_,_)=>WrapText(notice);
        main.Controls.Add(notice,0,1);main.Controls.Add(pageHost,0,2);shell.Controls.Add(main,1,1);
        var footer=new TableLayoutPanel{Dock=DockStyle.Fill,ColumnCount=1,Padding=new Padding(18,6,18,8),AccessibleName="Launcher status"};
        footer.ColumnStyles.Add(new ColumnStyle(SizeType.Percent,100));
        stage.Dock=DockStyle.Top;stage.AutoSize=true;stage.Height=24;stage.Padding=Padding.Empty;stage.Tag="wrap";stage.UseMnemonic=false;
        progress.Dock=DockStyle.Top;progress.Height=5;progress.Margin=new Padding(0,5,0,0);
        footer.Controls.Add(stage);footer.Controls.Add(progress);footer.Controls.Add(elapsedStatus);footer.SizeChanged+=(_,_)=>WrapText(footer);
        shell.Controls.Add(footer,0,2);shell.SetColumnSpan(footer,2);Controls.Add(shell);

        var play=Page("Play","Your village and connection, in one place.");
        play.Controls.Add(Card(Heading("Your village"),homeVillage,homeInstance,saveStatus,homeStatus,
            Row(ActionButton("Play",Play,true),ActionButton("Stop",Stop),ActionButton("Choose village",ChooseVillage),ActionButton("Refresh details",RefreshVillageDetails))));
        play.Controls.Add(Card([Heading("Setup checklist"),..checklist,Body("Play checks these steps every time. If setup pauses, follow the instructions and then retry.")]));

        var saves=Page("My Villages","Choose which village opens in BlueStacks. Switching villages does not delete your other saves.");
        saves.Controls.Add(Card(Heading("Saved villages"),Body("Select a village below, then choose Use selected village. Click Play when you are ready to open it."),villages,Row(ActionButton("Use selected village",UseSelectedVillage),ActionButton("Refresh list",RefreshVillageDetails))));
        saves.Controls.Add(Card(Heading("Coming from 0.2.6?"),Body("Extract your backup ZIP first. Select the old installation or private_state folder to import a copy; keep the original backup safe."),ActionButton("Import 0.2.6 save",async()=>{await ImportLegacy();})));

        var recovery=Page("Backups","Recovery copies are separate from your active village. A backup includes the complete database and its history.");
        recovery.Controls.Add(Card(Heading("Recovery copies"),backupStatus,backups,Row(ActionButton("Back up now",BackupNow),ActionButton("Open backup folder",OpenBackupFolder))));
        recovery.Controls.Add(Card(Heading("Keep your village safe"),Body("Successful game actions are saved as you play. Use Back up now before moving computers or changing versions. To recover an older village, stop the game and keep a copy of your current save first."),ActionButton("Recovery instructions",()=>{ShowPage("Help");return Task.CompletedTask;})));

        var helpPage=Page("Help","Start here if setup pauses or something in the game does not work.");
        helpPage.Controls.Add(Card(Heading("Getting started"),Body("1. Click Play and choose a new village or import your 0.2.6 save.\n2. Choose a dedicated BlueStacks 5 Pie 64-bit instance.\n3. Follow the setup instructions, including enabling Android Debug Bridge.\n4. Wait for the game to sign in, then play in BlueStacks.")));
        helpPage.Controls.Add(Card(Heading("Report a problem"),Body("Create a support report after reproducing the problem. The technical log shows where the report was saved. Review it before sharing it with community support."),Row(ActionButton("Create support report",Diagnostics),ActionButton("Open reports folder",()=>OpenFolder(Path.Combine(state,"reports"))))));
        helpPage.Controls.Add(Card(Heading("Recovering a save"),Body("Close the game and stop the server before restoring files. Keep the current database and backup unchanged until recovery is confirmed. Backups made before the new history format can be opened with the older launcher; migrated databases require this newer launcher."),ActionButton("Open save folder",OpenData)));
        var logsCard=Card(Heading("Technical log"),Body("Detailed activity and error codes for troubleshooting. No report is sent automatically."),output);
        output.Dock=DockStyle.Top;output.Height=220;output.WordWrap=true;output.AccessibleName="Technical log";
        helpPage.Controls.Add(logsCard);

        var settingsPage=Page("Settings","Manage setup and optional tools. Your current village is shown on Play.");
        settingsPage.Controls.Add(Card(Heading("BlueStacks and connection"),Body("Change the dedicated instance or run setup again. Stop the server before changing instances."),Row(ActionButton("Set up / change instance",Setup),ActionButton("Check connection",Connection))));
        settingsPage.Controls.Add(Card(Heading("Gems"),Body("Add a whole number of gems to a selected village. If the game is running, it restarts after the change is saved."),ActionButton("Add Gems",AddGems)));
        settingsPage.Controls.Add(Card(Heading("Appearance and language"),Body("Uses familiar Windows controls and display scaling. Launcher instructions are currently in English; the game's language remains separate.")));
        dashboardClock.Tick+=(_,_)=>{if(busy)elapsedStatus.Text=$"{currentAction} · {actionElapsed.Elapsed:mm\\:ss} elapsed";};dashboardClock.Start();
        FormClosed+=(_,_)=>selectedNavigationFont.Dispose();
        RenderChecklist();ShowPage("Play");
    }
    void ShowPage(string name) {
        currentPage=name;
        foreach(var pair in pages)pair.Value.Visible=pair.Key==name;
        foreach(var pair in navigation) {
            pair.Value.Font=pair.Key==name?selectedNavigationFont:Font;
            pair.Value.BackColor=pair.Key==name?SystemColors.Window:SystemColors.Control;
            pair.Value.AccessibleDescription=pair.Key==name?"Selected page":"Open "+pair.Key;
        }
        pageTitle.Text=name;pages[name].BringToFront();
    }
    void ShowTechnicalLog(){ShowPage("Help");output.Focus();output.SelectionStart=output.TextLength;output.ScrollToCaret();}
    bool ServerRunning=>backend is {HasExited:false};
    void BeginChecklist(){checklistRunning=true;checklistPosition=0;RenderChecklist();}
    void ChecklistStep(int completed){checklistPosition=completed;RenderChecklist();}
    void RenderChecklist() {
        string[] names=["Choose village","Connect BlueStacks","Prepare game files","Sign in and play"];
        for(int i=0;i<checklist.Length;i++) {
            var prefix=checklistPosition>i?"Done":checklistPosition==i&&checklistRunning?"Current":"To check";
            checklist[i].Text=$"{i+1}. {names[i]} — {prefix}";
        }
    }
    void UpdateDashboardStatus(string text) {
        homeStatus.Text=text;
        if(!ServerRunning && !checklistRunning && checklistPosition==4){checklistPosition=-1;RenderChecklist();}
    }
    async Task RunAction(string name,Func<Task> action) {
        if(busy||closing)return;
        busy=true;currentAction=name;actionElapsed.Restart();notice.Visible=false;
        string workingText="Working: "+name+"…";
        SetStage(0,workingText);
        elapsedStatus.Text=name+" · 00:00 elapsed";
        foreach(var button in actions)button.Enabled=false;
        retry.Enabled=false;progress.Style=ProgressBarStyle.Marquee;progress.MarqueeAnimationSpeed=25;
        try {
            await action();
            if(name!="Refresh village details" && name!="Refresh details" && name!="Refresh list") {
                try { await RefreshVillageDetails(); }
                catch(Exception e) { Log("Could not refresh village details. "+e.Message); }
            }
            if(stage.Text==workingText)SetStage(0,"Choose an action, or click Play to start or resume setup.");
        } catch(OperationCanceledException) {
            SetStage(0,"Cancelled. Click Play to resume setup when ready.");
        } catch(Exception e) {
            if(name.StartsWith("Refresh",StringComparison.Ordinal))saveStatus.Text="Save details could not be refreshed. This check does not change your village. Retry or open Backups.";
            retryAction=action;retryName=name;retry.Visible=true;
            noticeText.Text=FriendlyError(e.Message);notice.Visible=true;
            SetStage(0,"Could not complete this step. See the message above.");
            Log("[VL-TOOL-FAILED] "+e.Message);
        } finally {
            checklistRunning=false;RenderChecklist();busy=false;actionElapsed.Stop();
            if(!IsDisposed) {
                foreach(var button in actions)button.Enabled=true;
                retry.Enabled=true;progress.MarqueeAnimationSpeed=0;progress.Style=ProgressBarStyle.Blocks;progress.Value=0;
                elapsedStatus.Text=$"{name} · {actionElapsed.Elapsed:mm\\:ss} elapsed";
            }
        }
    }
    static string FriendlyError(string message) {
        if(message.Contains("Bundled new backend missing"))return "The launcher installation is incomplete: its game server is missing. Reinstall from the complete community installer, then retry. Keep your save folder and backups.";
        if(message.Contains("VL-BS-INSTANCE-UNSET"))return "Choose a BlueStacks instance to continue. Open Settings → Set up / change instance, or click Play for guided setup.";
        if(message.Contains("VL-BS-PORT-DIVERGED"))return "The selected BlueStacks instance has not finished configuring its connection. Open that instance once, finish its first-run prompts, then retry setup.";
        if(message.Contains("VL-SERVER-PORT-IN-USE")||message.Contains("server port is already in use"))return "Another program is using the game server port. Close any older Village Life launcher, then retry. Technical log has the details.";
        if(message.Contains("VL-OBB")||message.Contains("expansion"))return "The required game expansion could not be confirmed. Keep the selected BlueStacks instance open and retry setup. Your village has not been deleted.";
        if(message.Contains("VL-TOOL-TIMEOUT"))return "This step took longer than expected. Check the selected BlueStacks window for prompts, then retry.";
        if(message.Contains("VL-GUEST-BACKEND"))return "BlueStacks could not reach the local game server. Check the selected instance, then retry. Use Create support report if this continues.";
        return message.Length<=650?message:message[..650]+"… Open Technical log for details.";
    }
    async Task RefreshVillageDetails() {
        var settings=Read();homeVillage.Text=string.IsNullOrEmpty(settings.ImportedVillage)
            ? "Village linked to your selected BlueStacks instance" : "Imported 0.2.6 village";
        saveStatus.Text="Save details have not been confirmed yet.";
        homeInstance.Text="BlueStacks: not selected — click Play for guided setup";
        var binding=Path.Combine(state,"bluestacks-binding.json");
        if(File.Exists(binding)) {
            try {
                using var json=JsonDocument.Parse(File.ReadAllText(binding));
                homeInstance.Text="BlueStacks: "+json.RootElement.GetProperty("name").GetString()+" (selection saved; connection checked on Play)";
            } catch(Exception e) when(e is IOException or JsonException or KeyNotFoundException or InvalidOperationException) {homeInstance.Text="BlueStacks selection needs to be checked. Click Play to continue.";}
        }
        villages.Items.Clear();villageChoices.Clear();
        villageChoices.Add(("Use the village linked to the selected BlueStacks instance","",""));
        JsonElement[] localRows=[];
        if(File.Exists(defaultDatabase)) {
            using var local=await ReadVillageList("--db",defaultDatabase,"list-gem-villages");
            localRows=local.RootElement.EnumerateArray().Select(row=>row.Clone()).ToArray();
            foreach(var row in localRows)villageChoices.Add((LocalVillageLabel(row),"",row.GetProperty("village_id").GetString()!));
        }
        string database=VillageDatabase(settings);
        if(File.Exists(database)) {
            using var list=database==defaultDatabase?null:await ReadVillageList("--db",database,"list-gem-villages");
            var rows=list?.RootElement.EnumerateArray().ToArray()??localRows;
            JsonElement? selected=null;
            if(!string.IsNullOrEmpty(settings.LocalVillage))selected=rows.Where(row=>row.GetProperty("village_id").GetString()==settings.LocalVillage).Select(row=>(JsonElement?)row).FirstOrDefault();
            else if(rows.Length==1)selected=rows[0];
            if(selected is { } village) {
                homeVillage.Text=village.GetProperty("name").GetString()+$" · Level {village.GetProperty("level").GetInt32()} · {village.GetProperty("gems").GetDecimal():N0} gems";
                saveStatus.Text="Last recorded save: "+DateTimeOffset.FromUnixTimeSeconds(village.GetProperty("last_saved").GetInt64()).ToLocalTime().ToString("g")+". Refresh details to check again.";
            } else if(rows.Length>1)saveStatus.Text="This file contains several villages. Choose village to select one explicitly; otherwise BlueStacks uses its linked village.";
            else saveStatus.Text="No Woodland village listed yet. Complete the tutorial first, or select another saved village.";
        }
        else saveStatus.Text="No village file selected yet. Click Play to begin, or import your 0.2.6 save.";
        if(File.Exists(ServerExe) && Directory.Exists(Path.Combine(state,"imported-villages"))) {
            using var imported=await ReadVillageList("list-legacy-villages");
            foreach(var row in imported.RootElement.EnumerateArray())villageChoices.Add(("Imported — "+VillageLabel(row),row.GetProperty("key").GetString()!,""));
        }
        foreach(var choice in villageChoices)villages.Items.Add(choice.Label);
        villages.SelectedIndex=Math.Max(0,villageChoices.FindIndex(choice=>choice.Imported==settings.ImportedVillage && choice.Local==settings.LocalVillage));
        RefreshBackups(database);
    }
    Task UseSelectedVillage() {
        RequireStopped();
        if(villages.SelectedIndex<0||villages.SelectedIndex>=villageChoices.Count)throw new InvalidOperationException("Select a village from the list first.");
        var choice=villageChoices[villages.SelectedIndex];
        var settings=Read();settings.ImportedVillage=choice.Imported;settings.LocalVillage=choice.Local;settings.VillageChoiceMade=true;Write(settings);
        SetStage(0,"Village selected. Click Play to open it in BlueStacks.");Log("Selected: "+choice.Label);return Task.CompletedTask;
    }
    void RefreshBackups(string database) {
        backups.Items.Clear();
        var folders=new[]{Path.Combine(state,"backups"),Path.Combine(Path.GetDirectoryName(database)!,"backups")}.Distinct(StringComparer.OrdinalIgnoreCase);
        var files=folders.Where(Directory.Exists).SelectMany(folder=>Directory.EnumerateFiles(folder,"*.sqlite3")).Select(file=>new FileInfo(file)).OrderByDescending(file=>file.LastWriteTimeUtc).ToArray();
        foreach(var file in files.Take(100))backups.Items.Add($"{file.LastWriteTime:g} · {file.Name} · {file.Length/1048576.0:N1} MB");
        backupStatus.Text=files.Length==0?"No recovery backups found yet. Back up now after your village is created.":$"Latest backup file: {files[0].LastWriteTime:g}. {files.Length} recovery {(files.Length==1?"copy":"copies")} found.";
    }
    async Task BackupNow() {
        var database=VillageDatabase(Read());
        if(!File.Exists(database))throw new InvalidOperationException("There is no village database to back up yet. Click Play to create or import your village first.");
        var folder=Path.Combine(Path.GetDirectoryName(database)!,"backups");Directory.CreateDirectory(folder);
        var destination=Path.Combine(folder,$"{Path.GetFileNameWithoutExtension(database)}-manual-{DateTime.UtcNow:yyyyMMddTHHmmssZ}-{Guid.NewGuid():N}.sqlite3");
        SetStage(0,"Creating a complete recovery copy…");await ToolQuiet("--db",database,"backup-db",destination);
        SetStage(100,"Recovery backup created successfully.");Log("Created a complete recovery backup in Save Backups.");
    }
    Task OpenBackupFolder()=>OpenFolder(Path.Combine(Path.GetDirectoryName(VillageDatabase(Read()))!,"backups"));
    static Task OpenFolder(string folder){Directory.CreateDirectory(folder);Process.Start(new ProcessStartInfo(folder){UseShellExecute=true});return Task.CompletedTask;}
}
