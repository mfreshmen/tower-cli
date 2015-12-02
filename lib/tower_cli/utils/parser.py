# Copyright 2015, Ansible, Inc.
# Alan Rominger <arominger@ansible.com>
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

import yaml
import json

import ast
import shlex
import sys

from tower_cli.utils import exceptions as exc, debug


def parse_kv(var_string):
    """Similar to the Ansible function of the same name, parses file
    with a key=value pattern and stores information in a dictionary,
    but not as fully featured as the corresponding Ansible code."""
    return_dict = {}

    # Output updates dictionaries, so return empty one if no vals in
    if var_string is None:
        return {}

    # Python 2.6 / shlex has problems handling unicode, this is a fix
    fix_encoding_26 = False
    if sys.version_info < (2, 7) and '\x00' in shlex.split(u'a')[0]:
        fix_encoding_26 = True

    # Also hedge against Click library giving non-string type
    if fix_encoding_26 or not isinstance(var_string, str):
        var_string = str(var_string)

    # Use shlex library to split string by quotes, whitespace, etc.
    for token in shlex.split(var_string):

        # Second part of fix to avoid passing shlex unicode in py2.6
        if fix_encoding_26:
            token = unicode(token)
        # Look for key=value pattern, if not, process as raw parameter
        if '=' in token:
            (k, v) = token.split('=')
            # If '=' are unbalanced, then stop and warn user
            if len(k) == 0 or len(v) == 0:
                raise Exception
            # If possible, convert into python data type, for instance "5"->5
            try:
                return_dict[k] = ast.literal_eval(v)
            except:
                return_dict[k] = v
        else:

            # If there are spaces in the statement, there would be no way
            # split it from the rest of the text later, so check for that here
            if " " in token:
                token = '"' + token + '"'
            # If token is clearly a failed JSON or YAML string, don't advance
            if token.endswith(":"):
                raise Exception
            # Append the value onto the special key entry _raw_params
            # this uses a space delimiter
            if '_raw_params' in return_dict:
                return_dict['_raw_params'] += " " + token
            else:
                return_dict['_raw_params'] = token

    return return_dict


def string_to_dict(var_string, allow_kv=True):
    """Returns a dictionary given a string with yaml or json syntax.
    If data is not present in a key: value format, then it return
    an empty dictionary.

    Attempts processing string by 3 different methods in order:
        1. as JSON      2. as YAML      3. as custom key=value syntax
    Throws an error if all of these fail in the standard ways."""
    # try:
    #     # Accept all valid "key":value types of json
    #     return_dict = json.loads(var_string)
    #     assert type(return_dict) is dict
    # except (TypeError, AttributeError, ValueError, AssertionError):
    try:
        # Accept all JSON and YAML
        return_dict = yaml.load(var_string)
        assert type(return_dict) is dict
    except (AttributeError, yaml.YAMLError, AssertionError):
        # if these fail, parse by key=value syntax
        try:
            assert allow_kv
            return_dict = parse_kv(var_string)
        except:
            raise exc.TowerCLIError(
                'failed to parse some of the extra '
                'variables.\nvariables: \n%s' % var_string
            )
    return return_dict


def revised_update(dict1, dict2):
    """Updates dict1 with dict2 while appending the elements in _raw_params"""
    if '_raw_params' in dict2 and '_raw_params' in dict1:
        dict1['_raw_params'] += " " + str(dict2.pop('_raw_params'))
    return dict1.update(dict2)


def process_extra_vars(extra_vars_list, force_json=True):
    """Returns a string that is valid JSON or YAML and contains all the
    variables in every extra_vars_opt inside of extra_vars_list.

    Args:
       parse_kv (bool): whether to allow key=value syntax.
       force_json (bool): if True, always output json.
    """
    # Read from all the different sources and put into dictionary
    extra_vars = {}
    extra_vars_yaml = ""
    for extra_vars_opt in extra_vars_list:
        # Load file content if necessary
        if extra_vars_opt.startswith("@"):
            with open(extra_vars_opt[1:], 'r') as f:
                extra_vars_opt = f.read()
            # Convert text markup to a dictionary conservatively
            opt_dict = string_to_dict(extra_vars_opt, allow_kv=False)
        else:
            # Convert text markup to a dictionary liberally
            opt_dict = string_to_dict(extra_vars_opt, allow_kv=True)
        # Rolling YAML-based string combination
        if any(line.startswith("#") for line in extra_vars_opt.split('\n')):
            extra_vars_yaml += extra_vars_opt + "\n"
        elif extra_vars_opt != "":
            extra_vars_yaml += yaml.dump(
                opt_dict, default_flow_style=False) + "\n"
        # Combine dictionary with cumulative dictionary
        revised_update(extra_vars, opt_dict)

    # Return contents in form of a string
    if not force_json:
        try:
            # Conditions to verify it is safe to return rolling YAML string
            try_dict = yaml.load(extra_vars_yaml)
            assert type(try_dict) is dict
            debug.log('Using unprocessed YAML', header='decision', nl=2)
            return extra_vars_yaml.rstrip()
        except:
            debug.log('Failed YAML parsing, defaulting to JSON',
                      header='decison', nl=2)
    if extra_vars == {}:
        return ""
    return json.dumps(extra_vars)
