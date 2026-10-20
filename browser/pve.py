"""Validation and freshness for the optional nested Proxmox guest inventory."""
import math
import time

MAX_TEXT = 128
FRESH_SECONDS = 30


def _text(value, maximum=MAX_TEXT):
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ValueError('Invalid PVE text')
    return value


def _number(value, nullable=True):
    if value is None and nullable:
        return
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        raise ValueError('Invalid PVE number')


def _guest(guest, cluster_id, node):
    if not isinstance(guest, dict):
        raise ValueError('Invalid PVE guest')
    kind, vmid = guest.get('type'), guest.get('vmid')
    if kind not in ('qemu', 'lxc') or isinstance(vmid, bool) or not isinstance(vmid, int) or not 1 <= vmid <= 999999999:
        raise ValueError('Invalid PVE identity')
    expected_id = f'{cluster_id}:{kind}:{vmid}'
    if _text(guest.get('id'), 144) != expected_id or _text(guest.get('node')) != node:
        raise ValueError('Mismatched PVE identity')
    for key in ('name', 'status'):
        _text(guest.get(key))
    uptime, vcpus = guest.get('uptime'), guest.get('vcpus')
    _number(uptime)
    _number(vcpus)
    if vcpus is not None and (type(vcpus) is not int or vcpus < 1):
        raise ValueError('Invalid PVE vCPU count')
    if vcpus is not None and vcpus > 4096 or uptime is not None and uptime > 10**12:
        raise ValueError('PVE metric outside bounds')
    if guest.get('memory_basis') != 'pve':
        raise ValueError('Invalid PVE memory basis')
    cpu = guest.get('cpu')
    memory = guest.get('memory')
    if not isinstance(cpu, dict) or 'percent_total' not in cpu or not isinstance(memory, dict) or not isinstance(memory.get('ram'), dict):
        raise ValueError('Invalid PVE metric shape')
    _number(cpu.get('percent_total'))
    if cpu.get('percent_total') is not None and cpu['percent_total'] > 100:
        raise ValueError('Invalid PVE CPU percent')
    if not all(key in memory['ram'] for key in ('used', 'total', 'percent')):
        raise ValueError('Incomplete PVE RAM metrics')
    for key in ('used', 'total', 'percent'):
        value = memory['ram'][key]
        _number(value)
        if value is not None and value > 2**63 - 1:
            raise ValueError('PVE memory outside bounds')
    for metric in ('network_io', 'disk_io'):
        section = guest.get(metric)
        total = section.get('total') if isinstance(section, dict) else None
        rates = total.get('rate') if isinstance(total, dict) else None
        expected = ('rx_bytes_per_s', 'tx_bytes_per_s') if metric == 'network_io' else ('read_bytes_per_s', 'write_bytes_per_s')
        if not isinstance(rates, dict) or not all(key in rates for key in expected):
            raise ValueError('Invalid PVE IO metric shape')
        for key in expected:
            value = rates[key]
            _number(value)
            if value is not None and value > 2**63 - 1:
                raise ValueError('PVE IO value outside bounds')
    return {
        'id': expected_id, 'vmid': vmid, 'type': kind, 'node': node,
        'name': guest['name'], 'status': guest['status'],
        'uptime': uptime, 'vcpus': vcpus, 'memory_basis': 'pve',
        'cpu': {'percent_total': cpu['percent_total']},
        'memory': {'ram': {key: memory['ram'][key] for key in ('used', 'total', 'percent')}},
        'network_io': {'total': {'rate': {key: guest['network_io']['total']['rate'][key] for key in ('rx_bytes_per_s', 'tx_bytes_per_s')}}},
        'disk_io': {'total': {'rate': {key: guest['disk_io']['total']['rate'][key] for key in ('read_bytes_per_s', 'write_bytes_per_s')}}},
    }


def apply_virtualization(raw, previous=None):
    if not isinstance(raw, dict) or type(raw.get('version')) is not int or raw['version'] != 1 or raw.get('provider') != 'pve':
        raise ValueError('Unsupported virtualization contract')
    status = raw.get('status')
    if status not in ('ok', 'error', 'unconfigured'):
        raise ValueError('Invalid PVE status')
    cluster_id, node = raw.get('cluster_id'), raw.get('node')
    if status == 'ok':
        cluster_id, node = _text(cluster_id), _text(node)
    elif cluster_id is None and node is None:
        if 'guests' in raw:
            raise ValueError('Unconfigured PVE cannot claim an inventory')
        if previous:
            cluster_id, node = previous.get('cluster_id'), previous.get('node')
    else:
        cluster_id, node = _text(cluster_id), _text(node)
    observed = raw.get('observed_at')
    _number(observed)
    if observed is not None and observed > time.time() + 5:
        raise ValueError('Future PVE observation')
    result = {'version': 1, 'provider': 'pve', 'cluster_id': cluster_id, 'node': node, 'status': status}
    if raw.get('error') is not None:
        result['error'] = _text(raw['error'], 64)
    if status == 'ok':
        if observed is None:
            raise ValueError('Successful PVE observation needs a timestamp')
        guests = raw.get('guests')
        if not isinstance(guests, list):
            raise ValueError('Invalid PVE inventory')
        parsed = [_guest(item, cluster_id, node) for item in guests]
        ids = [item['id'] for item in parsed]
        if len(set(ids)) != len(ids):
            raise ValueError('Duplicate PVE guest')
        if (previous and previous.get('cluster_id') == cluster_id and previous.get('node') == node
                and previous.get('observed_at') is not None and observed < previous['observed_at']):
            return previous
        result.update(observed_at=observed, guests=parsed)
    else:
        if previous and (cluster_id is None or previous.get('cluster_id') == cluster_id and previous.get('node') == node):
            result.update({key: previous[key] for key in ('observed_at', 'guests') if key in previous})
        else:
            result['observed_at'] = observed
    return result


def snapshot_virtualization(value, now=None):
    if value is None:
        return None
    result = dict(value)
    stamp = result.get('observed_at')
    age = max(0, (time.time() if now is None else now) - stamp) if stamp is not None else None
    result.update(guest_count=len(result['guests']) if 'guests' in result else None,
                  fresh=age is not None and age <= FRESH_SECONDS,
                  age_seconds=round(age) if age is not None else None)
    return result
