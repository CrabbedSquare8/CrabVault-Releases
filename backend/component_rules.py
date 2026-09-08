"""Relações explícitas entre componentes de um mesmo mod."""
import copy


def validate(components):
    by_id = {c['id']: c for c in components}
    if len(by_id) != len(components):
        raise ValueError('Há componentes com IDs duplicados.')

    def closure(cid, visiting=None):
        visiting = set(visiting or ())
        if cid in visiting:
            raise ValueError('As dependências formam um ciclo.')
        visiting.add(cid)
        result = {cid}
        for dependency in by_id[cid].get('requires', []):
            if dependency not in by_id:
                raise ValueError('Uma dependência não existe neste mod.')
            result |= closure(dependency, visiting)
        groups = {}
        for item in result:
            group = str(by_id[item].get('exclusive_group') or '').strip().casefold()
            if group and group in groups and groups[group] != item:
                raise ValueError('Uma dependência exige duas alternativas incompatíveis do mesmo grupo.')
            if group:
                groups[group] = item
        return result

    return {cid: closure(cid) for cid in by_id}


def changed_state(components, component_id, enabled):
    result = copy.deepcopy(components)
    closures = validate(result)
    if component_id not in closures:
        raise ValueError('Componente não encontrado.')
    by_id = {c['id']: c for c in result}
    activate = closures[component_id] if enabled else set()
    groups = {str(by_id[c].get('exclusive_group') or '').strip().casefold() for c in activate} - {''}
    deactivate = {component_id} if not enabled else {
        c['id'] for c in result if c['id'] not in activate
        and str(c.get('exclusive_group') or '').strip().casefold() in groups}
    for c in result:
        if c['id'] in activate:
            c['enabled'] = True
        elif closures[c['id']] & deactivate:
            c['enabled'] = False
    assert_valid_state(result)
    return result


def assert_valid_state(components):
    closures = validate(components)
    active = {c['id'] for c in components if c.get('enabled', True)}
    groups = set()
    for c in components:
        if c['id'] not in active:
            continue
        if not closures[c['id']] <= active:
            raise ValueError('Ative os componentes necessários antes de ativar este complemento.')
        group = str(c.get('exclusive_group') or '').strip().casefold()
        if group and group in groups:
            raise ValueError('Mantenha somente uma alternativa ativa em cada grupo.')
        if group:
            groups.add(group)
