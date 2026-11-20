"""Deterministic original-client numeric villager IDs.

The canonical save keeps stable opaque IDs. Wire responses carry the
Villager_<player>_<numeric> identity expected by the native ARM client.
The mapping is deterministic, bounded to 24-bit suffixes and scoped per owner.
"""
from __future__ import annotations
import hashlib
import json

IDENTITY_KEYS={
    'requesterVillagerId','supplierVillagerId','id','ID','villagerId','VillagerStringID',
    'VillagerStringId','relativeVillagerId','partnerVillagerId','senderVillagerId',
    'recipientVillagerId','motherId','fatherId','neighborVillagerId','FriendCharacterId',
    'FriendCharacterID','CharacterID','villagerIds','VillagerIDs','CharacterIds','RetireVillagerIDs',
    'lightingVillagerId','villagerID','VillagerID','villagerStringId',
    'villagerStringID','motherVillagerId','fatherVillagerId',
}

def _actors(world:dict)->list[dict]:
    active = [e for e in world.get('world',{}).get('entities',[])
              if e.get('templateType')=='villager_type' and isinstance(e.get('id'),str)]
    return active + list(world.get('retiredVillagers', {}).values())

def _new_suffix(owner, ident, used):
    value = int(hashlib.sha256(f'{owner}:{ident}'.encode()).hexdigest()[:6], 16) or 1
    while value in used:
        value = value % 0xffffff + 1
    used.add(value)
    return str(value)


def reserve_ids(world, owner, pending):
    outward, _ = mappings(world, owner)
    registry = world.setdefault('nativeIdentityIds', {}).setdefault(owner, {})
    registry.update({ident: native.rsplit('_', 1)[1] for ident, native in outward.items()})
    used = {int(v) for v in registry.values()}
    for ident in pending:
        if ident not in registry:
            registry[ident] = _new_suffix(owner, ident, used)
    return registry


def mappings(world:dict,owner:str)->tuple[dict[str,str],dict[str,str]]:
    registry=world.get('nativeIdentityIds',{}).get(str(owner),{})
    used={int(x) for x in registry.values()}
    if len(used)!=len(registry) or any(x<=0 or x>0xffffff for x in used):
        raise ValueError('Invalid native identity registry')
    outward={};inward={}
    for actor in _actors(world):
        ident=actor['id'];suffix=registry.get(ident)
        if suffix is None:
            suffix=_new_suffix(owner, ident, used)
        native=f'Villager_{owner}_{suffix}'
        outward[ident]=native;inward[native]=ident;inward[str(suffix)]=ident
        legacy=str(int(hashlib.sha256(f'{owner}:{ident}'.encode()).hexdigest()[:12],16)+1)
        inward[f'Villager_{owner}_{legacy}']=ident;inward[legacy]=ident
    return outward,inward

def translate(value,mapping:dict[str,str],key:str|None=None):
    if isinstance(value,dict):return {k:translate(v,mapping,k) for k,v in value.items()}
    if isinstance(value,list):return [translate(v,mapping,key) for v in value]
    if isinstance(value,str) and key=='villagerIds' and value.lstrip().startswith(('[','{')):
        try:return json.dumps(translate(json.loads(value),mapping,key),separators=(',',':'))
        except (ValueError,TypeError):return value
    if key in IDENTITY_KEYS:return mapping.get(str(value),value)
    return value
