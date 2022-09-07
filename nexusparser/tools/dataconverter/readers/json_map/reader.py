#
# Copyright The NOMAD Authors.
#
# This file is part of NOMAD. See https://nomad-lab.eu for further info.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
"""An example reader implementation for the DataConverter."""
from typing import Tuple, Any
import json
import pickle
import numpy as np
import xarray

from nexusparser.tools.dataconverter.readers.base.reader import BaseReader
from nexusparser.tools.dataconverter.template import Template
from nexusparser.tools.dataconverter.helpers import ensure_all_required_fields_exist


def parse_slice(slice_string):
    """Converts slice strings to actual tuple sets of slices for index syntax"""
    slices = slice_string.split(",")
    for index, item in enumerate(slices):
        values = item.split(":")
        if len(values) == 1:
            slices[index] = int(values[0])
        else:
            if len(values) < 3:
                values.append("")
            slices[index] = slice(*tuple([int(x) if x != "" else None for x in values]))
    return np.index_exp[tuple(slices)]


def get_val_nested_keystring_from_dict(keystring, data):
    """
    Fetches data from the actual data dict using path strings without a leading '/':
        'path/to/data/in/dict'
    """
    if isinstance(keystring, (list, dict)):
        return keystring

    current_key = keystring.split("/")[0]
    if isinstance(data[current_key], dict):
        return get_val_nested_keystring_from_dict(keystring[keystring.find("/") + 1:],
                                                  data[current_key])
    if isinstance(data[current_key], xarray.DataArray):
        return data[current_key].values
    if isinstance(data[current_key], xarray.core.dataset.Dataset):
        raise Exception(f"Xarray datasets are not supported. "
                        f"You can only use xarray dataarrays.")

    return data[current_key]


def is_path(keystring):
    """Checks whether a given value in the mapping is a mapping path or just data"""
    return isinstance(keystring, str) and keystring[0] == "/"


def fill_undocumented(mapping, template, data):
    """Fill the extra paths provided in the map file that are not in the NXDL"""
    for path, value in mapping.items():
        if is_path(value):
            template["undocumented"][path] = get_val_nested_keystring_from_dict(value[1:],
                                                                                data)
        else:
            template["undocumented"][path] = value


def fill_documented(template, mapping, template_provided, data):
    """Fill the needed paths that are explicitly mentioned in the NXDL"""
    for req in ("required", "optional", "recommended"):
        for path in template_provided[req]:
            try:
                map_str = mapping[path]
                if is_path(map_str):
                    template[path] = get_val_nested_keystring_from_dict(map_str[1:],
                                                                        data)
                else:
                    template[path] = map_str

                del mapping[path]
            except KeyError:
                pass


def convert_shapes_to_slice_objects(mapping):
    """Converts shape slice strings to slice objects for indexing"""
    for key in mapping:
        if isinstance(mapping[key], dict):
            if "shape" in mapping[key]:
                mapping[key]["shape"] = parse_slice(mapping[key]["shape"])


class JsonMapReader(BaseReader):
    """A reader that takes a mapping json file and a data file/object to return a template."""

    # pylint: disable=too-few-public-methods

    # Whitelist for the NXDLs that the reader supports and can process
    supported_nxdls = ["NXtest", "*"]

    def read(self,
             template: dict = None,
             file_paths: Tuple[str] = None,
             objects: Tuple[Any] = None) -> dict:
        """
        Reads data from given file and returns a filled template dictionary.

        Only the data object is expected to be passed as the first object.
        Alteratively, a data object represented with a file.json or file.xarray.pickle
        can also be used.
        The mapping is only accepted as file.mapping.json to the inputs.
        """
        data: dict = {}
        mapping: dict = {}

        if objects:
            data = objects[0]

        for file_path in file_paths:
            file_extension = file_path[file_path.rindex("."):]
            if file_extension == ".json":
                with open(file_path, "r") as input_file:
                    if ".mapping" in file_path:
                        mapping = json.loads(input_file.read())
                    else:
                        data = json.loads(input_file.read())
            elif file_extension == ".pickle":
                with open(file_path, "rb") as input_file:  # type: ignore[assignment]
                    data = pickle.load(input_file)  # type: ignore[arg-type]

        convert_shapes_to_slice_objects(mapping)

        new_template = Template()
        fill_documented(new_template, mapping, template, data)

        fill_undocumented(mapping, new_template, data)

        ensure_all_required_fields_exist(template, new_template)

        return new_template


# This has to be set to allow the convert script to use this reader. Set it to "MyDataReader".
READER = JsonMapReader
