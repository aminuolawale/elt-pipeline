import pymongo
from pymongo import MongoClient
from dotenv import load_dotenv
import os
from pprint import pprint
import json
import sys

load_dotenv()
mongo_host = os.getenv("MONGO_HOST")
mongo_port = os.getenv("MONGO_PORT")
client = MongoClient(mongo_host, int(mongo_port))

type_table = {
    "float": "number",
    "str": "string",
    "int": "number",
    "bool": "boolean",
    "ObjectId": "string",
    "datetime": "string",
    "NoneType": "string",
}


def translate(value, table):
    if not table:
        return value
    for key, _value in table.items():
        if value == key:
            value = _value
            break
    return value


def handle_scalar(value):
    raw_type = type(value).__name__
    translated_type = translate(raw_type, type_table)
    field_schema = {"type": translated_type}
    if raw_type == "datetime":
        field_schema.update(format="date-time")
    return field_schema


def build_schema(doc):
    out = {"type": "object", "properties": {}}
    properties = out.get("properties")
    for key, value in doc.items():
        if type(value) == dict:
            properties.update({key: build_schema(value)})
        elif type(value) == list:
            if not value:
                continue
            if type(value[0]) not in [list, dict]:
                field_schema = handle_scalar(value[0])
                properties.update({key: field_schema})
            else:
                properties.update(
                    {key: {"type": "array", "items": build_schema(value[0])}}
                )
        else:
            field_schema = handle_scalar(value)
            properties.update({key: field_schema})
    return out


def generate_catalog(database_name, *selected_collections):
    database = getattr(client, database_name)
    stream = []
    if not selected_collections:
        selected_collections = database.list_collection_names()
        print(selected_collections)
    for collection in selected_collections:
        c = getattr(database, collection)
        if not c.count_documents({}):
            continue
        r = c.find().sort([("date_created", pymongo.DESCENDING)])[0]
        schema = build_schema(r)
        pprint(schema)
        stream_entry = {
            "table_name": collection,
            "stream": collection,
            "metadata": [
                {
                    "breadcrumb": [],
                    "metadata": {
                        "table-key-properties": ["_id"],
                        "database-name": database_name,
                        "row-count": c.count_documents({}),
                        "is-view": False,
                        "valid-replication-keys": ["_id"],
                        "selected": True,
                        "replication-method": "LOG_BASED",
                    },
                }
            ],
            "tap_stream_id": f"{database_name}-{collection}",
            "schema": schema,
            "selected": True,
        }
        stream.append(stream_entry)
    extractor_catalog_path = os.path.join(
        os.getcwd(), database_name, "extract", "tap-mongodb.catalog.json"
    )
    try:
        with open(extractor_catalog_path, "w") as e:
            catalog = {"stream": stream}
            e.write(json.dumps(catalog))
    except:
        pass


def generate_catalogs(database_name, *selected_collections):
    print(database_name)
    if not database_name or database_name == "__all__":
        dbs = client.list_database_names()
        for db in dbs:
            if "sendbox" in db:
                generate_catalog(db)
    else:
        generate_catalog(database_name, *selected_collections)


def delete_catalogs(*database_names):
    if len(database_names) == 1 and database_names[0] == "__all__":
        database_names = [d for d in client.list_database_names()]
    for d in database_names:
        cat_path = os.path.join(os.getcwd(), d, "extract", "tap-mongodb.catalog.json")
        if os.path.exists(cat_path):
            os.remove(cat_path)


if __name__ == "__main__":
    # generate_catalog()
    thismodule = sys.modules[__name__]
    argv = sys.argv
    if len(argv) > 1:
        func = getattr(thismodule, argv[1])
        if len(argv) > 2:
            func(*argv[2:])
        else:
            func()
    else:
        print("Please pass function in argv")