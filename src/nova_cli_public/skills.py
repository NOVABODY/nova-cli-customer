"""Authenticated workflow guidance; never a grant of business authority."""
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

NAME = Annotated[str, Field(pattern=r'^nova-[a-z0-9-]+$', max_length=64)]
FILE = Annotated[str, Field(pattern=r'^(?:SKILL\.md|(?:references|templates)/(?:[a-z0-9_-]+/)*[a-z0-9_-]+\.md)$', max_length=250)]
INSTRUCTIONS = (
    ' Use list_skills to find Nova workflows. Read nova-fora-basics with get_skill, '
    'then read the skill and listed references needed for the task. Skills grant no permissions. / '
    'Usa list_skills para buscar flujos de Nova. Lee nova-fora-basics con get_skill. '
    'Después, lee la habilidad y las referencias necesarias. Las habilidades no conceden permisos.'
)


class Empty(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class GetSkill(Empty):
    name: NAME
    file: FILE = 'SKILL.md'


class SkillSummary(BaseModel):
    model_config = ConfigDict(strict=True)
    name: NAME
    description: str = Field(min_length=1, max_length=1024)
    version: str
    language: str
    files: list[FILE] = Field(min_length=1, max_length=100)


class SkillCatalog(BaseModel):
    model_config = ConfigDict(strict=True)
    required_skill: NAME
    items: list[SkillSummary] = Field(max_length=100)


class SkillDocument(BaseModel):
    model_config = ConfigDict(strict=True)
    name: NAME
    file: FILE
    content: str = Field(min_length=1, max_length=131072)


MODELS = {'list_skills': Empty, 'get_skill': GetSkill}
OUTPUTS = {'list_skills': SkillCatalog, 'get_skill': SkillDocument}


def validated(name, value, arguments):
    result = OUTPUTS[name].model_validate(value)
    if name == 'get_skill' and (result.name != arguments['name'] or result.file != arguments.get('file', 'SKILL.md')):
        raise ValueError('Mismatched skill document')
    return result.model_dump()


def run(args):
    from nova_cli_public import legacy_reads
    from nova_cli_public.errors import ApiError

    name = args.skill_tool
    arguments = MODELS[name].model_validate({key: getattr(args, key) for key in MODELS[name].model_fields}).model_dump()
    path = '/agent-skills' + ('/' + arguments['name'] if name == 'get_skill' else '')
    value = legacy_reads.client_from_args(args).request('GET', path,
        query={'file': arguments['file']} if name == 'get_skill' else {})
    try:
        return validated(name, value, arguments)
    except ValueError:
        raise ApiError('Invalid skill response. / Respuesta de habilidad no válida.') from None


COMMANDS = [
    {'command': 'skills list', 'tool': 'list_skills', 'grant': None, 'authenticated_guidance': True,
     'description': 'List Nova workflow skills. / Lista habilidades de flujos de Nova.',
     'arguments': [], 'groups': [], 'handler': run, 'defaults': {'skill_tool': 'list_skills'}},
    {'command': 'skills get', 'tool': 'get_skill', 'grant': None, 'authenticated_guidance': True,
     'description': 'Read a Nova skill or listed reference. / Lee una habilidad de Nova o una referencia de la lista.',
     'arguments': [(['--name'], {'required': True}), (['--file'], {'default': 'SKILL.md'})],
     'groups': [], 'handler': run, 'defaults': {'skill_tool': 'get_skill'}},
]
