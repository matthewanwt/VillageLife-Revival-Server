using System.Diagnostics;
using System.Windows.Forms;

namespace VillageLife;

public sealed partial class VillageLifeWindow {
    readonly System.Windows.Forms.Timer gameMonitor=new() { Interval=15000 };
    Process? monitoredBackend;
    bool checkingGame;
    int absentChecks;

    void StartGameMonitoring(Process process) {
        monitoredBackend=process;
        absentChecks=0;
        gameMonitor.Start();
    }

    void StopGameMonitoring() {
        gameMonitor.Stop();
        monitoredBackend=null;
    }

    async void CheckGameClosed(object? sender, EventArgs args) {
        var process=monitoredBackend;
        if (process is null || busy || closing || checkingGame) return;
        if (process.HasExited) {
            StopGameMonitoring();
            SetStage(0,"Local server exited. Click Play to reconnect.");
            return;
        }
        checkingGame=true;
        try {
            var result=await Once(25,"original-game-status");
            if (monitoredBackend!=process || busy || closing || IsDisposed) return;
            bool closed=result.Item1==0 && result.Item2.Trim()=="closed";
            bool disconnected=result.Item1!=0 && IsCode(result.Item3.Trim(),"VL-ADB-NOT-READY","VL-ADB-UNAVAILABLE");
            absentChecks=closed || disconnected ? absentChecks+1 : 0;
            if (absentChecks<(closed ? 2 : 3)) return;
            busy=true;
            try {
                Log("The game closed or the selected BlueStacks instance disconnected.");
                await Stop();
            } finally { busy=false; }
        } catch (TimeoutException) {
            // A slow status check is inconclusive.
            absentChecks=0;
        } catch (Exception e) {
            Log("Could not check the game window. "+e.Message);
        } finally { checkingGame=false; }
    }
}
