"""Original loopback community channel for the private NPC provider."""
from __future__ import annotations

import time
import uuid

from villagelife.support import record_missing, record_original_call
from .randomness import new_state
from .relationships import COMMUNITY_SERVICES
from .sessions import ClientIdentity

EMPTY_LISTS = {
    'UserMessage/GetInbox': ('UserMessages', 'FriendshipRequests', 'GroupRequests',
                             'GroupInvites', 'ChatroomInvites', 'GlobalMessageDetails'),
    'Friendship/GetByUser': ('Users', 'Groups', 'MasterUsers', 'Friendships'),
    'MaterialRequest/GetReceived': ('MaterialRequests',),
    'Group/GetTop': ('Groups',),
    'User/GetTop': ('Users', 'Groups'),
}


class CommunityRules:
    def __init__(self, repo, sessions, dating):
        self.repo = repo
        self.sessions = sessions
        self.dating = dating
        self.active_identity: ClientIdentity | None = None

    def identify(self, document):
        owner = str(document.get('UserId', 0))
        if 'sessionId' in document or 'deviceId' in document:
            try:
                identity = self.sessions.authenticate({**document, 'pId': owner})
            except (ValueError, PermissionError):
                return None
            return identity
        # The native community envelope supplies UserId only. The private
        # loopback server binds that envelope to its latest authenticated game
        # session, regardless of how many older devices are in the database.
        active = self.active_identity
        return active if active is not None and active.player_id == owner else None

    def dispatch(self, ident, service, data):
        if not isinstance(data, dict):
            raise ValueError('Community action data must be an object')
        state = None
        if ident is not None:
            payload = self.repo.read_village(ident.village_id).payload
            state = (payload.get('originalSave') or {}).get('normal')
        if service in COMMUNITY_SERVICES:
            if ident is None:
                if service == 'CharacterRequest/GetReceived':
                    return {'CharacterRequests': []}
                raise PermissionError('Community identity unavailable')
            if state is None:
                if service == 'CharacterRequest/GetReceived':
                    return {'CharacterRequests': []}
                raise ValueError('Normal world required for dating')
            at = int(time.time())
            if service == 'CharacterRequest/GetReceived':
                return self.dating.inbox(state, at, ident.player_id)

            def apply(payload):
                save = payload['originalSave']
                if service == 'CharacterRequest/Delete':
                    return self.dating.remove(save['normal'], data, at)
                rng = save.get('rng')
                if rng is None:
                    rng = save['rng'] = new_state()
                return self.dating.create(save['normal'], data, at, ident.player_id, rng)

            _, result, _ = self.repo.mutate(ident.village_id, operation_key=f'community:{uuid.uuid4()}',
                                            request={'service': service, 'data': data}, change=apply)
            return result

        if service in EMPTY_LISTS:
            return {key: [] for key in EMPTY_LISTS[service]}
        if service not in {'User/Get', 'ApplicationSetting/Get'}:
            raise NotImplementedError('Community operation not implemented')
        profile = state.get('user', {}) if state else {}
        result = {'User': {'Id': int(ident.player_id) if ident else 1,
                           'Name': profile.get('name', 'Local Village'), 'GroupId': 0,
                           'IsAcceptingInvites': False, 'XpLevel': profile.get('userLevelID', 1)},
                  'Group': {}}
        if service == 'ApplicationSetting/Get':
            result['ApplicationSettings'] = [{'Key': key, 'Value': '0'} for key in (
                'ChatEnabled', 'MaxFriendsPerPlayer', 'MaxPlayersInGroupChatroom',
                'MaxPlayersInPrivateChatroom', 'MaxPrivateChatroomsPerPlayer')]
        return result

    def process(self, document):
        calls = document.get('Calls')
        if (not isinstance(calls, list) or not 1 <= len(calls) <= 250
                or any(not isinstance(c, dict) for c in calls)):
            raise ValueError('Community calls array required')
        ident = self.identify(document)
        results = []
        for call in calls:
            service = call.get('Service')
            data = call.get('Data', {})
            code, message, result = 200, '', {}
            try:
                if not isinstance(service, str) or len(service) > 160:
                    raise ValueError('Invalid community service')
                result = self.dispatch(ident, service, data)
            except PermissionError as exc:
                code, message = 403, str(exc)
            except (KeyError, TypeError, ValueError) as exc:
                code, message = 400, str(exc)[:200]
            except NotImplementedError as exc:
                code, message = 501, str(exc)
            if isinstance(service, str):
                try:
                    if code == 501:
                        record_missing(self.repo, 'RPC', service, code)
                    record_original_call(self.repo, service, code, result, data, message)
                except Exception:
                    pass
            response = {'Id': call.get('Id', call.get('Id:')), 'code': code, 'Data': result}
            if message:
                response['message'] = message
            results.append(response)
        return {'code': 200, 'data': results}

