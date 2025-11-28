import os
import sys
import jsonschema
from importlib.resources import files
import yaml
from pathlib import Path
import shutil
import copy


def recursive_merge(dict1, dict2):
    result = copy.deepcopy(dict1)

    for key, value in dict2.items():
        if key in result:
            if isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = recursive_merge(result[key], value)

            elif isinstance(result[key], list) and isinstance(value, list):
                # merge lists uniquely while keeping order
                seen = set()
                new_list = []
                for item in result[key] + value:
                    if item not in seen:
                        seen.add(item)
                        new_list.append(item)
                result[key] = new_list

            else:
                result[key] = copy.deepcopy(value)
        else:
            result[key] = copy.deepcopy(value)

    return result


# this method gets called indirectly via the pve_cloud ansible collection
# if there is a pve.cloud collection playbook is passed in the system args
# we can load a schema extension aswell
def validate_inventory(inventory, load_schema_ext=True):
    # load base schema
    base_schema_name = inventory["plugin"].removeprefix("pve.cloud.")

    with (files("pve_cloud_schemas.definitions") / f"{base_schema_name}_schema.yaml").open("r") as f:
        schema = yaml.safe_load(f)

    if load_schema_ext:
        called_pve_cloud_playbook = None
        for arg in sys.argv:
            if arg.startswith("pve.cloud."):
                called_pve_cloud_playbook = arg.split('.')[-1].removeprefix("pve.cloud.")

        if called_pve_cloud_playbook:
            # playbook call look for schema extension
            extension_file = files("pve_cloud_schemas.extensions") / f"{called_pve_cloud_playbook}_schema_ext.yaml"

            if extension_file.is_file(): # schema extension exists
                with extension_file.open("r") as f:
                    schema_ext = yaml.safe_load(f)

                # merge with base schema 
                schema = recursive_merge(schema, schema_ext)

    
    jsonschema.validate(instance=inventory, schema=schema)



def validate_inventory_file():
    with open(sys.argv[1], "r") as f:
        inventory = yaml.safe_load(f)
    
    validate_inventory(inventory)


def dump_schemas():
    dump_po = Path(sys.argv[1])
    dump_po.mkdir(parents=True, exist_ok=True)

    schemas = files("pve_cloud_schemas.definitions")
    for schema in schemas.iterdir():
        with schema.open("rb") as src, (dump_po / schema.name).open("wb") as dest:
            shutil.copyfileobj(src, dest)

    # map schemas to their plugin id
    schema_map = {}

    for schema in schemas.iterdir():
        with schema.open("r") as f:
            schema_loaded = yaml.safe_load(f)
        
        schema_map[schema_loaded["properties"]["plugin"]["enum"][0]] = schema_loaded

    # load schema extensions, merge and dump
    for schema_ext in files("pve_cloud_schemas.extensions").iterdir():
        with schema_ext.open("r") as f:
            schema_ext_loaded = yaml.safe_load(f)
        
        schema_merged = recursive_merge(schema_map[schema_ext_loaded["properties"]["plugin"]["enum"][0]], schema_ext_loaded)

        # write it
        with (dump_po / schema_ext.name).open("w") as f:
            yaml.dump(schema_merged, f, sort_keys=False, indent=2)