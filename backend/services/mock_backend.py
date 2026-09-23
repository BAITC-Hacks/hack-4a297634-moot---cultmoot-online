import copy
import json
import secrets

class MockBackend:
    def __init__(self,path):
        data=json.loads(path.read_text(encoding='utf-8'))
        self.clients={c['client_id']:c for c in data['clients']}

    def execute(self,state,scenario,action,slots,capability=None):
        spec=scenario.action_specs.get(action)
        if not spec: return {'ok':False,'mock':True,'error':'action_not_integrated'}
        op,collection=spec.get('operation'),spec.get('collection')
        if op not in {'lookup','update','create'} or collection not in {'cards','loans','deposits','transfers','devices'}:
            return {'ok':False,'mock':True,'error':'unsupported_backend_operation'}
        if op!='lookup' and not capability: raise ValueError('confirmation_required')
        client_id=slots.get('client_id')
        if client_id not in self.clients: return {'ok':False,'mock':True,'error':'synthetic_client_not_found'}
        client=state.mock_records.setdefault(client_id,copy.deepcopy(self.clients[client_id]))
        records=client.get(collection,[])
        if op=='create':
            records.append({'id':'DEMO-'+secrets.token_hex(4),'status':spec['value']})
        elif op=='update':
            if not records: return {'ok':False,'mock':True,'error':'record_not_found'}
            records[0]['status']=spec['value']
        return {'ok':True,'mock':True,'operation':op,'collection':collection,'records':copy.deepcopy(records),
                'confirmation_receipt':capability[:12] if capability else None}
