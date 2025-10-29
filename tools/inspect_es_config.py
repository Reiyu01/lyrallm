from lyrallm.config.config_manager import config_manager
from lyrallm.adapters import es_client
import json

print('vectordb:')
print(json.dumps(config_manager.config.get('vectordb', {}), indent=2, ensure_ascii=False))
print('\nstorages:')
print(json.dumps(config_manager.config.get('storages', {}), indent=2, ensure_ascii=False))
print('\nes_client._get_es_config():')
print(json.dumps(es_client._get_es_config(), indent=2, ensure_ascii=False))
