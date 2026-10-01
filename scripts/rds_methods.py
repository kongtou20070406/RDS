"""Review declared method scopes; never interpret prose or grant authorization."""
from copy import deepcopy


def _text(value, limit=2048):
    return isinstance(value, str) and bool(value.strip()) and len(value) <= limit


def _fields(value):
    return (isinstance(value, dict) and len(value) <= 8 and
            all(_text(k, 64) and _text(v, 128) for k, v in value.items()))


def declared_methods(item):
    """A missing description remains unknown, including in a composed action."""
    value = item.get('methods')
    if value is None:
        return [{}]
    rows = [value] if isinstance(value, dict) else value
    if not isinstance(rows, list) or not 1 <= len(rows) <= 32 or not all(_fields(r) for r in rows):
        raise ValueError('methods must describe 1..32 steps using bounded string fields')
    return deepcopy(rows)


def _match(expected, actual):
    if any(k in actual and actual[k] != v for k, v in expected.items()):
        return False
    return True if all(k in actual for k in expected) else None


def review_methods(context, methods):
    """Exact scoped predicates on caller reports, separate from proof and budget."""
    constraints = context.get('method_constraints', [])
    if not isinstance(constraints, list) or len(constraints) > 32:
        raise ValueError('method_constraints must contain at most 32 sourced clauses')
    report = {'status': 'UNCONSTRAINED', 'assurance': 'INPUT_REPORTED',
              'issues': [], 'questions': []}
    if not constraints:
        return report
    seen = set()
    for clause in constraints:
        if (not isinstance(clause, dict) or not _text(clause.get('id'), 128) or clause['id'] in seen
                or not _text(clause.get('quote')) or not _text(clause.get('source'))
                or clause.get('status') not in {'CONFIRMED', 'UNRESOLVED'}
                or not _fields(clause.get('when', {}))):
            raise ValueError('Each method constraint needs a unique id, original quote, source, status and scoped when')
        seen.add(clause['id'])
        predicates = [key for key in ('forbid', 'require') if key in clause]
        if clause['status'] == 'CONFIRMED' and (len(predicates) != 1 or
                not _fields(clause[predicates[0]]) or not clause[predicates[0]]):
            raise ValueError('A confirmed method constraint needs exactly one nonempty forbid or require predicate')
        if 'question' in clause and not _text(clause['question']):
            raise ValueError('A clarification question must be bounded nonempty text')
        confirmation = clause.get('confirmation')
        if confirmation is not None and (not isinstance(confirmation, dict) or
                not _text(confirmation.get('quote')) or not _text(confirmation.get('source'))):
            raise ValueError('A method clarification must retain its actual quote and source')
    profiles = declared_methods({'methods': methods})
    report.update(status='COMPATIBLE', checked_steps=len(profiles))
    questioned = set()
    for index, profile in enumerate(profiles):
        for clause in constraints:
            applicable = _match(clause.get('when', {}), profile)
            if applicable is False:
                continue
            if clause['status'] == 'UNRESOLVED':
                status, reason = 'UNKNOWN', 'The affected interpretation needs human clarification'
                if clause['id'] not in questioned:
                    questioned.add(clause['id'])
                    report['questions'].append({'constraint_id': clause['id'], 'quote': clause['quote'],
                        'source': clause['source'], 'question': clause.get('question') or
                        'Which method steps does this restriction cover? Confirm its scope before dependent work.'})
            elif applicable is None:
                status, reason = 'UNKNOWN', 'Describe the step before deciding whether the restriction applies'
            else:
                kind = 'forbid' if 'forbid' in clause else 'require'
                matched = _match(clause[kind], profile)
                conflict = matched is True if kind == 'forbid' else matched is False
                status = 'UNKNOWN' if matched is None else 'CONFLICT' if conflict else 'COMPATIBLE'
                reason = 'Missing method fields' if matched is None else 'Declared step conflicts with the scoped restriction'
            if status != 'COMPATIBLE':
                report['issues'].append({'step': index, 'constraint_id': clause['id'], 'status': status, 'reason': reason})
                if status == 'CONFLICT' or report['status'] == 'COMPATIBLE':
                    report['status'] = status
    return report


def review_candidate(context, candidate):
    """Annotate only opted-in contexts; READY labels cannot bypass this review."""
    if 'method_constraints' not in context:
        return None
    item = candidate.get('action', candidate)
    report = review_methods(context, item.get('methods'))
    candidate['method_review'] = report
    if report['status'] == 'CONFLICT':
        candidate['status'] = 'BLOCKED_METHOD'
    elif report['status'] == 'UNKNOWN' and candidate.get('status') == 'READY':
        candidate['status'] = 'NEEDS_METHOD_CLARIFICATION' if report['questions'] else 'NEEDS_METHOD_DESCRIPTION'
    return report
