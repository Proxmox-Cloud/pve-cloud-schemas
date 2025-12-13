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


def load_inheritance(loaded_schema):
    if "inherit_schema" in loaded_schema:
        # schema to inherit, drill down
        with (files("pve_cloud_schemas.definitions") / loaded_schema["inherit_schema"]).open("r") as f:
            inherit_schema = yaml.safe_load(f)

        # will keep recursing down to the absolute base schema
        
        schema = load_inheritance(inherit_schema)
        return recursive_merge(schema, loaded_schema)

    # then it will return that base schema and keep merging the extenting schemas into it
    return loaded_schema


# this method gets called indirectly via the pve_cloud ansible collection
# if there is a pve.cloud collection playbook is passed in the system args
# we can load a schema extension aswell
def validate_inventory(inventory, load_schema_ext=True):
    # load base schema
    base_schema_name = inventory["plugin"].removeprefix("pve.cloud.")

    # load schema with inheritance
    with (files("pve_cloud_schemas.definitions") / f"{base_schema_name}_schema.yaml").open("r") as f:
        schema = load_inheritance(yaml.safe_load(f))

    schema.pop("inherit_schema", None) # remove the inheritance key if it exists

    # add the playbook extension ontop
    if load_schema_ext:
        called_pve_cloud_playbook = None
        for arg in sys.argv:
            if arg.startswith("pve.cloud."):
                called_pve_cloud_playbook = arg.split('.')[-1].removeprefix("pve.cloud.")
            if arg.startswith("playbooks/"): # execution in e2e tests
                called_pve_cloud_playbook = arg.removeprefix("playbooks/").removesuffix(".yaml")

        if called_pve_cloud_playbook:
            # playbook call look for schema extension
            extension_file = files("pve_cloud_schemas.extensions") / f"{called_pve_cloud_playbook}_schema_ext.yaml"

            if extension_file.is_file(): # schema extension exists
                with extension_file.open("r") as f:
                    schema_ext = yaml.safe_load(f)

                schema_ext.pop("extend_schema", None) # remove the extension key

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

    # map schemas to their plugin id
    schema_map = {}

    schemas = files("pve_cloud_schemas.definitions")
    for schema in schemas.iterdir():
        print("loading schema", schema.name)
        # load schema with inheritance
        with schema.open("r") as f:
            schema_loaded = load_inheritance(yaml.safe_load(f))

        schema_loaded.pop("inherit_schema", None) # remove the inheritance key if it exists
        
        # dump the inherited schema
        with (dump_po / schema.name).open("w") as f:
            yaml.dump(schema_loaded, f, sort_keys=False, indent=2)

        schema_map[schema.name] = schema_loaded

    # load schema extensions, merge and dump
    for schema_ext in files("pve_cloud_schemas.extensions").iterdir():
        with schema_ext.open("r") as f:
            schema_ext_loaded = yaml.safe_load(f)
        
        schema_merged = recursive_merge(schema_map[schema_ext_loaded["extend_schema"]], schema_ext_loaded)

        schema_merged.pop("extend_schema", None) # remove the extension key

        # write it
        with (dump_po / schema_ext.name).open("w") as f:
            yaml.dump(schema_merged, f, sort_keys=False, indent=2)