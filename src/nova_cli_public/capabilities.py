"""Offline discovery of registered customer commands; never a permission grant."""

import argparse

from nova_cli_public import __version__
from nova_cli_public.errors import UsageError
from nova_cli_public.fleet import ARGUMENTS, OUTPUTS

# Only effect/usage information lives here. Arguments come from the real parser;
# fleet input/output contracts come from the same models used during execution.
DETAILS = {
    'capabilities': ('List the commands in this client. No account access is checked.',
                     ['local_read'], 'nova capabilities --json'),
    'profile set': ('Save an API profile and select it. Use a separate profile for each API host.',
                    ['local_config_write'], 'nova profile set personal --api https://nova.example/api'),
    'profile use': ('Select a saved profile.', ['local_config_write'], 'nova profile use personal'),
    'profile show': ('Read a saved profile.', ['local_read'], 'nova profile show personal'),
    'profile list': ('List saved profiles.', ['local_read'], 'nova profile list'),
    'profile remove': ('Delete a profile and its local credentials; the server connection remains.',
                       ['local_config_write', 'local_credentials_delete'], 'nova profile remove personal'),
    'auth login': ('Open browser sign-in and consent. Store the refresh token in the OS keyring.',
                   ['browser_handoff', 'remote_authorization', 'local_credentials_write'],
                   'nova auth login'),
    'auth status': ('Check local credential presence. This does not check server authorization.',
                    ['local_credentials_read'], 'nova auth status'),
    'auth refresh': ('Rotate the connection refresh token.',
                     ['remote_authorization', 'local_credentials_write'], 'nova auth refresh'),
    'auth logout': ('Delete local credentials; the server connection remains. Disconnect it in browser settings.',
                    ['local_credentials_delete'], 'nova auth logout'),
    'vehicle list': ('List active fleet vehicles that the account can read.',
                     ['remote_read'], 'nova vehicle list --page 1 --per-page 20'),
    'vehicle get': ('Read a vehicle from the fleet list.',
                    ['remote_read'], 'nova vehicle get VAN-0001'),
}


def command_parsers(parser, prefix=()):
    children = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    if not children:
        yield ' '.join(prefix), parser
    for action in children:
        for name, child in action.choices.items():
            yield from command_parsers(child, (*prefix, name))


def argument_schema(parser):
    properties, required, arguments = {}, [], []
    for action in parser._actions:
        if action.dest == 'help':
            continue
        positional = not action.option_strings
        schema = {'type': 'integer' if action.type is int else 'string'}
        if isinstance(action, (argparse._StoreTrueAction, argparse._StoreFalseAction)):
            schema = {'type': 'boolean'}
        if action.choices is not None:
            schema['enum'] = list(action.choices)
        if action.default not in (None, argparse.SUPPRESS):
            schema['default'] = action.default
        properties[action.dest] = schema
        if action.required:
            required.append(action.dest)
        arguments.append({'name': action.dest, 'flags': action.option_strings,
                          'positional': positional, 'required': action.required, **schema})
    return {'type': 'object', 'properties': properties, 'required': required,
            'additionalProperties': False}, arguments


def manifest(parser, selected=None):
    commands = []
    for name, leaf in command_parsers(parser):
        description, effects, example = DETAILS[name]
        schema, arguments = argument_schema(leaf)
        entry = {
            'id': name.replace(' ', '.'), 'command': name, 'description': description,
            'effects': effects, 'examples': [example], 'arguments': arguments,
            'input_schema': schema, 'availability': 'implemented',
            'authorization': 'not_checked', 'required_scope': None,
        }
        if name.startswith('vehicle '):
            tool = 'list_vehicles' if name == 'vehicle list' else 'get_vehicle'
            tool_schema = ARGUMENTS[tool].model_json_schema()
            entry['input_schema'] = {**tool_schema, 'properties': {
                **tool_schema['properties'],
                **{key: schema['properties'][key] for key in ('profile', 'json')},
            }}
            entry.update(tool_input_schema=tool_schema,
                         output_schema=OUTPUTS[tool].model_json_schema(), mcp_tool=tool,
                         required_scope='nova:read',
                         api={'method': 'GET', 'path': '/assistant/vehicles' +
                              ('/{vehicle_id}' if tool == 'get_vehicle' else '')})
        if name in ('auth login', 'auth refresh'):
            entry['required_scope'] = 'nova:read'
        if selected is None or selected == name:
            commands.append(entry)
    if not commands:
        raise UsageError('Unknown customer command. Run nova capabilities for the full list.')
    return {
        'schema_version': 1, 'client_version': __version__, 'executables': ['nova', 'nova-cli', 'nova-mcp'],
        'authorization': 'not_checked', 'full_customer_parity': False,
        'help_command': 'nova --help', 'version_command': 'nova --version',
        'authorization_note': 'Offline discovery does not check the deployment, connection, role, '
                              'tenant, or record permissions. The API checks each request.',
        'coverage_document': 'docs/CustomerParity.md',
        'mcp': {'command': 'nova-mcp --profile PROFILE', 'transport': 'stdio',
                'install_extra': 'nova-cli[mcp]', 'requires': 'Saved profile and browser login',
                'tools': list(ARGUMENTS), 'authorization': 'not_checked'},
        'commands': commands,
    }


def render_toc(value):
    lines = [f"Nova CLI {value['client_version']} — available commands",
             'Account authorization: not checked. Full DSP/vendor parity: not yet available.', '']
    lines.extend(f"nova {c['command']} — {c['description']}" for c in value['commands'])
    lines.extend(['', 'Use --json for argument schemas, effects, scopes, and examples.',
                  'Use --command "vehicle get" to inspect one command.',
                  'See docs/CustomerParity.md for workflow coverage and remaining work.'])
    return '\n'.join(lines)
