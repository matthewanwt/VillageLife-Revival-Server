using System.Globalization;
using System.Text.Json;
using System.Windows.Forms;

namespace VillageLife;

public sealed partial class VillageLifeWindow {
    async Task AddGems() {
        var settings=Read();
        var database=VillageDatabase(settings);
        if (!File.Exists(database))
            throw new InvalidOperationException("Play through the tutorial to Woodland before adding gems.");
        using var list=await ReadVillageList("--db",database,"list-gem-villages");
        var villages=list.RootElement.EnumerateArray().ToArray();
        if (villages.Length==0)
            throw new InvalidOperationException("Play through the tutorial to Woodland before adding gems.");
        var labels=villages.Select(row=>$"{row.GetProperty("name").GetString()} (level {row.GetProperty("level").GetInt32()}, {row.GetProperty("gems").GetDecimal():N0} gems) · saved {DateTimeOffset.FromUnixTimeSeconds(row.GetProperty("last_saved").GetInt64()).ToLocalTime():g}").ToArray();
        int selected=villages.Length==1 ? 0 : PickVillage("Choose a village for Add Gems",
            "This save contains multiple villages. Choose the one that should receive the gems.",labels,-1);
        if (selected<0) return;
        var villageId=villages[selected].GetProperty("village_id").GetString()!;
        using var dialog=new Form {
            Text="Add Gems", StartPosition=FormStartPosition.CenterParent,
            FormBorderStyle=FormBorderStyle.FixedDialog, MaximizeBox=false, MinimizeBox=false,
            AutoScaleMode=AutoScaleMode.Font, AutoSize=true, AutoSizeMode=AutoSizeMode.GrowAndShrink
        };
        var layout=SetupDialogLayout(480);
        layout.Controls.Add(SetupText($"Add gems to {labels[selected]}. If the game is open, it will restart after the gems have been saved.",480));
        var amount=new TextBox {Text="1000", Width=200};
        var add=SetupButton("Add Gems");
        var cancel=SetupButton("Cancel",DialogResult.Cancel);
        var error=SetupText("",480);
        error.AccessibleName="Gem amount validation";
        int value=0;
        add.Click+=(_,_)=>{
            var digits=amount.Text.Trim();
            if (digits.Any(character=>!char.IsAsciiDigit(character))
                || !int.TryParse(digits,NumberStyles.None,CultureInfo.InvariantCulture,out value)
                || value<1 || value>2_000_000_000) {
                error.Text="Enter a whole number from 1 to 2,000,000,000 using digits only.";
                amount.Focus();
                amount.SelectAll();
                return;
            }
            dialog.DialogResult=DialogResult.OK;
        };
        amount.TextChanged+=(_,_)=>error.Text="";
        layout.Controls.Add(amount);
        layout.Controls.Add(error);
        layout.Controls.Add(SetupButtons(cancel,add));
        dialog.Controls.Add(layout);
        dialog.AcceptButton=add;
        dialog.CancelButton=cancel;
        dialog.ActiveControl=amount;
        amount.Select(0,amount.Text.Length);
        if (dialog.ShowDialog(this)!=DialogResult.OK) return;
        bool restart=backend is {HasExited:false};
        SetStage(25,"Adding gems to your selected village…");
        using var result=JsonDocument.Parse(await ReadTool(60,"--db",database,"add-local-gems",
            value.ToString(CultureInfo.InvariantCulture),"--village-id",villageId));
        var balance=result.RootElement.GetProperty("balance").GetDecimal();
        Log($"Added {value:N0} gems. Your balance is {balance:N0}.");
        SetStage(100,"Gems added to your selected village.");
        if (restart) { await Stop(); await Play(); }
    }
}
