import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
import trace_arm_protocol as t
parts=['StateLoadUser','ParseAllWants','SentRequestParser','NotificationParser','InboxUser','MessageParser','Wants','StateLoadArea','WorldModelJSON','LoadMyWorld','SetXP','HUD','VillagerCountPopulation','SetCameraControl','StatePlayGamePanWorld','ShrineUpdate','ShrineDisplay','ShrineSetup','GetUserLevelFromXP','StatePlayGame','WantsView','ShowHUD','SetHUD','ParseUser']
for s in t.SYMBOLS:
 if s['defined']=='True' and any(p in s['name'] for p in parts):
  result=t.trace(s)
  (t.OUT/(s['name']+'.txt')).write_text('\n'.join(result['disassembly']),encoding='utf8')
  print(s['name'],sorted(set(v['text'] for v in result['string_references'])))



