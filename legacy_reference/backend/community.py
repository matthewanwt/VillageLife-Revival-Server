"""Recovered community settings envelope; local deployment disables online chat."""
def process(document,user=None,relationship_operation=None):
 calls=document.get('Calls',[])
 if not isinstance(calls,list) or not calls:raise ValueError('Community calls required')
 responses=[]
 for call in calls:
  ident=call.get('Id',call.get('Id:'))
  if call.get('Service') in {'CharacterRequest/Create','CharacterRequest/GetReceived','CharacterRequest/Delete'} and relationship_operation is not None:
   try:
    data=call.get('Data',{})
    if not isinstance(data,dict):raise ValueError('Community action data must be an object')
    result=relationship_operation(call['Service'],data);responses.append({'Id':ident,'code':200,'Data':result})
   except PermissionError as error:responses.append({'Id':ident,'code':403,'Data':{},'message':str(error)})
   except ValueError as error:responses.append({'Id':ident,'code':400,'Data':{},'message':str(error)})
   except NotImplementedError as error:responses.append({'Id':ident,'code':501,'Data':{},'message':str(error)})
  elif call.get('Service')=='User/Get':
   record={'Id':1,'Name':'Local Village','GroupId':0,'IsAcceptingInvites':False,'XpLevel':1,**(user or {})}
   responses.append({'Id':ident,'code':200,'Data':{'User':record,'Group':{}}})
  elif call.get('Service') in {'UserMessage/GetInbox','Friendship/GetByUser','CharacterRequest/GetReceived','MaterialRequest/GetReceived','Group/GetTop','User/GetTop'}:
   fields={'UserMessage/GetInbox':['UserMessages','FriendshipRequests','GroupRequests','GroupInvites','ChatroomInvites','GlobalMessageDetails'],'Friendship/GetByUser':['Users','Groups','MasterUsers','Friendships'],'CharacterRequest/GetReceived':['CharacterRequests'],'MaterialRequest/GetReceived':['MaterialRequests'],'Group/GetTop':['Groups'],'User/GetTop':['Users','Groups']}[call['Service']]
   responses.append({'Id':ident,'code':200,'Data':{k:[] for k in fields}})
  elif call.get('Service')!='ApplicationSetting/Get':
   responses.append({'Id':ident,'code':501,'Data':{},'message':'Community operation not implemented'})
  else:
   settings=[{'Key':key,'Value':'0'} for key in ['ChatEnabled','MaxFriendsPerPlayer','MaxPlayersInGroupChatroom','MaxPlayersInPrivateChatroom','MaxPlayersInPublicChatroom','MaxPrivateChatroomsPerPlayer']]
   responses.append({'Id':ident,'code':200,'Data':{'ApplicationSettings':settings,'User':user or {'Id':1,'Name':'Local Village','GroupId':0,'IsAcceptingInvites':False,'XpLevel':1},'Group':{}}})
 return {'code':200,'data':responses}
