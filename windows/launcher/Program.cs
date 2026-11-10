using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Windows.Forms;
internal static class Program {
 [STAThread] static void Main(string[] args) {
  if(args.Length>0 && args[0].StartsWith("--")){Environment.ExitCode=LocalApkSigner.Run(args);return;}
  using var single=new Mutex(true,"VillageLifeLauncher_"+Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(AppContext.BaseDirectory)))[..16],out bool first);
  if(!first){MessageBox.Show("Village Life is already open.");return;}
  ApplicationConfiguration.Initialize();Application.Run(new PlayWindow());
 }
}
sealed class PlayWindow:Form {
 readonly string root=Path.GetFullPath(Path.Combine(AppContext.BaseDirectory,".."));
 readonly Button play=new(){Text="Play / Restart",AutoSize=true};
 readonly Button stop=new(){Text="Stop",AutoSize=true,Enabled=false};
 readonly Button setup=new(){Text="Set Up Game",AutoSize=true};
 readonly TextBox log=new(){Multiline=true,ReadOnly=true,ScrollBars=ScrollBars.Vertical,Dock=DockStyle.Fill};
 Process? runner;bool settingUp,closing;
 public PlayWindow(){
  Text="Village Life";Width=820;Height=430;MinimumSize=new(680,340);StartPosition=FormStartPosition.CenterScreen;
  var row=new FlowLayoutPanel(){Dock=DockStyle.Top,Height=48,Padding=new(6)};
  var connection=new Button(){Text="Connection",AutoSize=true};var saves=new Button(){Text="Save Backups",AutoSize=true};var logs=new Button(){Text="Logs",AutoSize=true};var network=new Button(){Text="Network Check",AutoSize=true};var diagnostics=new Button(){Text="Export Diagnostics",AutoSize=true};var missing=new Button(){Text="Export Missing Requests",AutoSize=true};var manager=new Button(){Text="Instance Manager",AutoSize=true};var help=new Button(){Text="Help",AutoSize=true};
  row.AutoScroll=true;row.WrapContents=false;row.Controls.AddRange([play,stop,setup,manager,connection,saves,logs,network,diagnostics,missing,help]);Controls.Add(log);Controls.Add(row);
  connection.Click+=(_,_)=>Connection();
  play.Click+=async(_,_)=>await Play();stop.Click+=async(_,_)=>await Stop();setup.Click+=async(_,_)=>await Setup();
  saves.Click+=(_,_)=>Folder("backups");logs.Click+=(_,_)=>Folder("experiments");network.Click+=async(_,_)=>await NetworkCheck();diagnostics.Click+=async(_,_)=>await ExportDiagnostics();missing.Click+=async(_,_)=>await ExportMissingRequests();manager.Click+=async(_,_)=>await OpenInstanceManager();
  help.Click+=(_,_)=>MessageBox.Show(this,"First use: install BlueStacks 5, click Instance Manager to create a dedicated Pie 64-bit instance (or select an existing dedicated one), enable its ADB setting, then close it. Click Set Up Game and select that instance from the list.\n\nFor daily play, open Village Life.exe. Keep this window open. Your village is saved locally and backed up before each play session.\n\nGoogle/Facebook sign-in is not required. Dismiss any offline sign-in error yourself with Back.\n\nThe gem-purchase + button remains a known crash. The building shop is separate. Multiplayer hosting is still in private testing.","Village Life help");
  Shown+=async(_,_)=>{if(Configured())await Play();else Say("Welcome. Click Set Up Game for first use. If a game archive is included, setup uses it automatically. Help explains the BlueStacks steps.");};
  FormClosing+=async(_,e)=>{if(closing)return;e.Cancel=true;closing=true;await Stop();if(closing)Close();};
 }
 void Connection(){
  if(runner is {HasExited:false}){Say("Stop the game before changing its connection.");return;}
  string file=Path.Combine(root,"play-settings.json");var values=File.Exists(file)?JsonSerializer.Deserialize<Dictionary<string,object>>(File.ReadAllText(file))!:new Dictionary<string,object>();
  string Value(string key)=>values.TryGetValue(key,out var value)?value.ToString()??"":"";
  using var dialog=new Form(){Text="Village Life connection",Width=520,Height=290,StartPosition=FormStartPosition.CenterParent,FormBorderStyle=FormBorderStyle.FixedDialog,MaximizeBox=false,MinimizeBox=false};
  var online=new CheckBox(){Text="Use an online server",Left=18,Top=15,Width=350,Checked=Value("server_mode")=="online"};
  var address=new TextBox(){Left=140,Top=52,Width=340,Text=Value("server_url")};var code=new TextBox(){Left=140,Top=88,Width=340,Text=Value("join_code"),UseSystemPasswordChar=true};
  var save=new Button(){Text="Save",Left=395,Top=200,Width=85};var cancel=new Button(){Text="Cancel",Left=300,Top=200,Width=85,DialogResult=DialogResult.Cancel};
  dialog.Controls.AddRange([online,new Label(){Text="Server address",Left=18,Top=55,Width=120},address,new Label(){Text="Private join code",Left=18,Top=91,Width=120},code,new Label(){Text="Offline uses this PC's village. Online uses the host's village. Switching modes does not merge saves. Online requires an invitation; multiplayer remains in private testing.",Left=18,Top=130,Width=465,Height=60},save,cancel]);
  void Fields(){address.Enabled=online.Checked;code.Enabled=online.Checked;}online.CheckedChanged+=(_,_)=>Fields();Fields();
  save.Click+=(_,_)=>{
   if(online.Checked&&(!Uri.TryCreate(address.Text.Trim(),UriKind.Absolute,out var uri)||uri.Scheme!="https"||uri.UserInfo!=""||uri.Query!=""||uri.Fragment!=""||code.Text.Trim().Length<20)){MessageBox.Show(dialog,"Enter the host's HTTPS address and private join code.");return;}
   values["server_mode"]=online.Checked?"online":"local";values["server_url"]=address.Text.Trim();values["join_code"]=code.Text.Trim();
   string temporary=file+".tmp";File.WriteAllText(temporary,JsonSerializer.Serialize(values,new JsonSerializerOptions(){WriteIndented=true}));File.Move(temporary,file,true);dialog.DialogResult=DialogResult.OK;dialog.Close();Say(online.Checked?"Online connection saved. The host keeps the online village.":"Offline play selected. Your local village will be used.");
  };
  dialog.CancelButton=cancel;dialog.ShowDialog(this);
 }
 void Folder(string relative){string path=Path.Combine(root,relative);Directory.CreateDirectory(path);Process.Start(new ProcessStartInfo(path){UseShellExecute=true});}
 void Say(string text){if(IsDisposed)return;if(InvokeRequired){BeginInvoke(()=>Say(text));return;}log.AppendText(text+Environment.NewLine);}
 bool Configured(){try{using var doc=JsonDocument.Parse(File.ReadAllText(Path.Combine(root,"play-settings.json")));return doc.RootElement.TryGetProperty("instance",out _)&&doc.RootElement.TryGetProperty("adb_port",out _);}catch{return false;}}
 string Python(){using var doc=JsonDocument.Parse(File.ReadAllText(Path.Combine(AppContext.BaseDirectory,"launcher.json")));string path=doc.RootElement.GetProperty("python").GetString()!;return Path.IsPathRooted(path)?path:Path.Combine(root,path);}
 async Task Play(){
  if(runner is {HasExited:false}){if(settingUp){Say("Setup is still running. Please wait.");return;}await runner.StandardInput.WriteLineAsync("restart");await runner.StandardInput.FlushAsync();return;}
  await Run("tools/play_local.py",[],false);
 }
 async Task Setup(){
  if(runner is {HasExited:false}){Say("Stop the game before running setup.");return;}
  string selected;
  setup.Enabled=false;play.Enabled=false;
  try{
   var info=new ProcessStartInfo(Python()){WorkingDirectory=root,UseShellExecute=false,CreateNoWindow=true,RedirectStandardOutput=true,RedirectStandardError=true,StandardOutputEncoding=Encoding.UTF8,StandardErrorEncoding=Encoding.UTF8};
   info.Environment["PYTHONIOENCODING"]="utf-8:replace";info.Environment["PYTHONUTF8"]="1";
   info.ArgumentList.Add(Path.Combine(root,"tools","setup_local.py"));info.ArgumentList.Add("--list-instances");
   using var query=Process.Start(info)!;var output=query.StandardOutput.ReadToEndAsync();var errors=query.StandardError.ReadToEndAsync();await query.WaitForExitAsync();
   if(query.ExitCode!=0)throw new Exception(await errors+await output);
   using var doc=JsonDocument.Parse(await output);var options=doc.RootElement.EnumerateArray().Select(item=>new {Id=item.GetProperty("id").GetString()!,Name=item.GetProperty("name").GetString()!}).ToArray();
   if(options.Length==0)throw new Exception("No Pie64 instances found. Click Instance Manager to create a dedicated Pie 64-bit instance, enable ADB, then close it before setup.");
   using var dialog=new Form(){Text="Choose your Village Life instance",Width=620,Height=245,StartPosition=FormStartPosition.CenterParent,FormBorderStyle=FormBorderStyle.FixedDialog,MaximizeBox=false,MinimizeBox=false};
   var choices=new ComboBox(){Left=18,Top=76,Width=565,DropDownStyle=ComboBoxStyle.DropDownList};choices.Items.AddRange(options.Select(item=>(object)(item.Name+"  ["+item.Id+"]")).ToArray());choices.SelectedIndex=options.Length==1?0:-1;
   if(File.Exists(Path.Combine(root,"play-settings.json"))){using var saved=JsonDocument.Parse(File.ReadAllText(Path.Combine(root,"play-settings.json")));if(saved.RootElement.TryGetProperty("instance",out var existing)){int index=Array.FindIndex(options,item=>item.Id==existing.GetString());if(index>=0)choices.SelectedIndex=index;}}
   var ok=new Button(){Text="Use this instance",Left=420,Top=150,Width=160,DialogResult=DialogResult.OK};ok.Enabled=choices.SelectedIndex>=0;choices.SelectedIndexChanged+=(_,_)=>ok.Enabled=choices.SelectedIndex>=0;var cancel=new Button(){Text="Cancel",Left=310,Top=150,Width=100,DialogResult=DialogResult.Cancel};
   dialog.Controls.AddRange([new Label(){Text="Select the NEW dedicated instance you created for Village Life.\nAny display name is allowed. Enable ADB and close that instance first.",Left=18,Top=18,Width=565,Height=48},choices,ok,cancel]);dialog.AcceptButton=ok;dialog.CancelButton=cancel;
   if(dialog.ShowDialog(this)!=DialogResult.OK)return;var choice=options[choices.SelectedIndex];selected=choice.Id;
   if(MessageBox.Show(this,"Configure "+choice.Name+" ["+choice.Id+"] for Village Life?\n\nThis configures the selected instance's NAT host-loopback settings and installs the game. The NAT configuration alone is NOT an internet isolation guarantee. Wi-Fi-on safety must pass guest checks; other instances are not intentionally changed.","Set up Village Life",MessageBoxButtons.OKCancel)!=DialogResult.OK)return;
  }catch(Exception ex){Say("Unable to list instances: "+ex.Message);return;}finally{setup.Enabled=true;play.Enabled=true;}
  var args=new List<string>{"--yes","--instance",selected};
  if(File.Exists(Path.Combine(root,"COMMUNITY-PACKAGE.json")) && !File.Exists(Path.Combine(root,"analysis","local-client","changes.json")) && !Directory.EnumerateFiles(root,"*.xapk").Any()){
   using var picker=new OpenFileDialog(){Title="Select your original Village Life XAPK",Filter="Village Life XAPK (*.xapk)|*.xapk",CheckFileExists=true};
   if(picker.ShowDialog(this)!=DialogResult.OK)return;
   args.Add("--source");args.Add(picker.FileName);
  }
  await Run("tools/setup_local.py",args.ToArray(),true);
 }
 async Task Run(string script,string[] args,bool isSetup){
  play.Enabled=false;setup.Enabled=false;
  try{
   string python=Python();if(!File.Exists(python))throw new Exception("The included runtime is missing. Extract the complete package again.");
   var info=new ProcessStartInfo(python){WorkingDirectory=root,UseShellExecute=false,CreateNoWindow=true,RedirectStandardInput=true,RedirectStandardOutput=true,RedirectStandardError=true,StandardOutputEncoding=Encoding.UTF8,StandardErrorEncoding=Encoding.UTF8};
   info.Environment["PYTHONIOENCODING"]="utf-8:replace";info.Environment["PYTHONUTF8"]="1";
   info.ArgumentList.Add("-u");info.ArgumentList.Add(Path.Combine(root,script));foreach(var arg in args)info.ArgumentList.Add(arg);
   settingUp=isSetup;runner=Process.Start(info)!;stop.Enabled=true;var current=runner;
   _=Read(current.StandardOutput);_=Read(current.StandardError);
   _=Task.Run(async()=>{await current.WaitForExitAsync();if(!IsDisposed)BeginInvoke(()=>{if(runner==current){stop.Enabled=false;play.Enabled=true;setup.Enabled=true;Say(isSetup?(current.ExitCode==0?"Setup complete. Click Play / Restart.":"Setup needs attention. See the message above."):"Stopped. Your save is retained.");}});});
  }catch(Exception ex){Say("Unable to start: "+ex.Message);setup.Enabled=true;}finally{play.Enabled=true;}
  await Task.CompletedTask;
 }
 async Task Read(StreamReader stream){try{while(await stream.ReadLineAsync() is string line)Say(line);}catch(ObjectDisposedException){}catch(IOException ex){Say(ex.Message);}}
 async Task NetworkCheck(){
  try{
   var info=new ProcessStartInfo(Python()){
    WorkingDirectory=root,UseShellExecute=false,CreateNoWindow=true,
    RedirectStandardOutput=true,RedirectStandardError=true,
    StandardOutputEncoding=Encoding.UTF8,StandardErrorEncoding=Encoding.UTF8
   };
   info.Environment["PYTHONIOENCODING"]="utf-8:replace";
   info.Environment["PYTHONUTF8"]="1";
   info.ArgumentList.Add("-u");
   info.ArgumentList.Add(Path.Combine(root,"tools","diagnose_network.py"));
   Say("Collecting read-only BlueStacks/Wi-Fi diagnostics. No network rules will be changed.");
   using var process=Process.Start(info) ?? throw new IOException("Could not start network diagnostic");
   var stdout=process.StandardOutput.ReadToEndAsync();
   var stderr=process.StandardError.ReadToEndAsync();
   using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(40));
   try{await process.WaitForExitAsync(timeout.Token);}
   catch(OperationCanceledException){process.Kill(entireProcessTree:true);Say("Network check timed out [VL-NET-DIAG-TIMEOUT]. Please export diagnostics.");return;}
   Say((await stdout).Trim());
   if(process.ExitCode!=0)Say("Network diagnostic failed [VL-NET-DIAG-FAILED]: "+(await stderr).Trim());
   else Say("You can include the network report in Export Diagnostics. It is not proof of isolation.");
  }catch(Exception ex){Say("Network diagnostic unavailable [VL-NET-DIAG-FAILED]: "+ex.GetType().Name);}
 }
 async Task ExportDiagnostics(){
  try{
   var info=new ProcessStartInfo(Python()){
    WorkingDirectory=root,UseShellExecute=false,CreateNoWindow=true,
    RedirectStandardOutput=true,RedirectStandardError=true,
    StandardOutputEncoding=Encoding.UTF8,StandardErrorEncoding=Encoding.UTF8
   };
   info.Environment["PYTHONIOENCODING"]="utf-8:replace";
   info.Environment["PYTHONUTF8"]="1";
   info.ArgumentList.Add("-u");
   info.ArgumentList.Add(Path.Combine(root,"tools","export_diagnostics.py"));
   using var process=Process.Start(info) ?? throw new IOException("Could not start diagnostic exporter");
   var stdout=process.StandardOutput.ReadToEndAsync();
   var stderr=process.StandardError.ReadToEndAsync();
   await process.WaitForExitAsync();
   Say((await stdout).Trim());
   if(process.ExitCode!=0)Say("Diagnostic export failed: "+(await stderr).Trim());
   else Say("Inspect the support ZIP before sending it privately to a developer. No saves are included.");
  }catch(Exception ex){Say("Could not export diagnostics: "+ex.Message);}
 }
 async Task ExportMissingRequests(){
  await RunOneShotTool("export_missing_requests.py", "Missing-request report", TimeSpan.FromSeconds(20));
 }
 async Task OpenInstanceManager(){
  await RunOneShotTool("open_instance_manager.py", "BlueStacks Multi-instance Manager", TimeSpan.FromSeconds(20), "--open-manager");
 }
 async Task RunOneShotTool(string script,string label,TimeSpan timeout,string? argument=null){
  try{
   var info=new ProcessStartInfo(Python()){
    WorkingDirectory=root,UseShellExecute=false,CreateNoWindow=true,
    RedirectStandardOutput=true,RedirectStandardError=true,
    StandardOutputEncoding=Encoding.UTF8,StandardErrorEncoding=Encoding.UTF8
   };
   info.Environment["PYTHONIOENCODING"]="utf-8:replace";
   info.Environment["PYTHONUTF8"]="1";
   info.ArgumentList.Add("-u");
   info.ArgumentList.Add(Path.Combine(root,"tools",script.Replace('/',Path.DirectorySeparatorChar)));
   if(argument is not null)info.ArgumentList.Add(argument);
   using var process=Process.Start(info) ?? throw new IOException("Could not start " + label);
   var stdout=process.StandardOutput.ReadToEndAsync();
   var stderr=process.StandardError.ReadToEndAsync();
   using var cancellation=new CancellationTokenSource(timeout);
   try{await process.WaitForExitAsync(cancellation.Token);}
   catch(OperationCanceledException){process.Kill(entireProcessTree:true);Say(label + " timed out [VL-TOOL-TIMEOUT].");return;}
   if(process.ExitCode==0)Say((await stdout).Trim());
   else { string details=((await stderr)+(await stdout)).Trim(); Say(label+" failed [VL-TOOL-FAILED]: "+details[..Math.Min(500,details.Length)]); }
  }catch(Exception ex){Say(label+" unavailable [VL-TOOL-FAILED]: "+ex.GetType().Name);}
 }
 async Task Stop(){
  var current=runner;if(current is null||current.HasExited)return;play.Enabled=false;stop.Enabled=false;
  try{
   if(settingUp){current.Kill(entireProcessTree:true);await current.WaitForExitAsync();Say("Setup stopped. It can be run again.");return;}
   await current.StandardInput.WriteLineAsync("stop");await current.StandardInput.FlushAsync();using var timeout=new CancellationTokenSource(TimeSpan.FromSeconds(30));await current.WaitForExitAsync(timeout.Token);
  }catch(OperationCanceledException){Say("Still stopping. Keep this window open and check the logs.");closing=false;stop.Enabled=true;}catch(Exception ex){Say(ex.Message);closing=false;}finally{play.Enabled=true;setup.Enabled=true;}
 }
}
