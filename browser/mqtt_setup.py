#!/usr/bin/env python3
"""Validate MQTT credentials and subscription before saving a private configuration."""
import argparse
import getpass
import json
import os
from pathlib import Path
import socket
import ssl
import sys


class Rejected(Exception):
    pass


def validate(config):
    if not isinstance(config, dict):
        raise ValueError('MQTT configuration must be an object')
    if not isinstance(config.get('host'), str) or not config['host'].strip():
        raise ValueError('MQTT broker host is required')
    if type(config.get('port', 1883)) is not int or not 1 <= config.get('port', 1883) <= 65535:
        raise ValueError('MQTT port must be 1-65535')
    if type(config.get('tls', False)) is not bool:
        raise ValueError('MQTT tls must be true or false')
    for key in ('username', 'password', 'topic'):
        value = config.get(key, 'sys/agents/+/metrics' if key == 'topic' else '')
        if not isinstance(value, str) or '\0' in value or len(value.encode()) > 65535:
            raise ValueError('Invalid MQTT ' + key)
    if not config.get('topic', 'sys/agents/+/metrics'):
        raise ValueError('MQTT topic must not be empty')
    if config.get('password') and not config.get('username'):
        raise ValueError('MQTT password requires a username')


def string(value):
    value = value.encode()
    return len(value).to_bytes(2, 'big') + value


def send(stream, kind, body):
    size, length = len(body), bytearray()
    while True:
        digit, size = size % 128, size // 128
        length.append(digit | (128 if size else 0))
        if not size:
            break
    stream.sendall(bytes([kind]) + length + body)


def receive(stream):
    def exact(size):
        data = bytearray()
        while len(data) < size:
            part = stream.recv(size - len(data))
            if not part:
                raise OSError('MQTT broker closed connection')
            data.extend(part)
        return bytes(data)
    kind, size, multiplier = exact(1)[0], 0, 1
    for _ in range(4):
        digit = exact(1)[0]
        size += (digit & 127) * multiplier
        if not digit & 128:
            if size > 1024:
                raise OSError('Unexpected MQTT handshake packet size')
            return kind, exact(size)
        multiplier *= 128
    raise OSError('Invalid MQTT packet length')


def probe(config):
    """MQTT 3.1.1 CONNECT + QoS 0 subscription, without displaying broker data."""
    validate(config)
    with socket.create_connection((config['host'], config.get('port', 1883)), timeout=8) as raw:
        stream = ssl.create_default_context().wrap_socket(raw, server_hostname=config['host']) if config.get('tls') else raw
        try:
            flags = 2
            payload = string('hwmonitor-setup-' + os.urandom(6).hex())
            if config.get('username'):
                flags |= 128
                payload += string(config['username'])
                if config.get('password'):
                    flags |= 64
                    payload += string(config['password'])
            send(stream, 0x10, string('MQTT') + bytes([4, flags, 0, 15]) + payload)
            kind, body = receive(stream)
            if kind != 0x20 or len(body) != 2:
                raise OSError('Invalid MQTT CONNACK')
            if body[1] in (4, 5):
                raise Rejected('MQTT login rejected')
            if body[1]:
                raise OSError('MQTT broker refused connection (code %d)' % body[1])
            send(stream, 0x82, b'\x00\x01' + string(config.get('topic', 'sys/agents/+/metrics')) + b'\x00')
            kind, body = receive(stream)
            if kind != 0x90 or len(body) != 3 or body[:2] != b'\x00\x01':
                raise OSError('Invalid MQTT SUBACK')
            if body[2] == 128:
                raise Rejected('MQTT subscription rejected')
            if body[2] not in (0, 1, 2):
                raise OSError('Invalid MQTT subscription result')
            send(stream, 0xe0, b'')
        finally:
            if stream is not raw:
                stream.close()


def setup(config, interactive):
    if not isinstance(config, dict):
        raise ValueError('MQTT configuration must be an object')
    while True:
        if not config.get('host'):
            if not interactive:
                raise ValueError('Supply --config FILE or MQTT_HOST; interactive setup needs a terminal')
            config['host'] = input('MQTT broker host: ').strip()
            config['tls'] = input('MQTT TLS? [y/N]: ').strip().lower() == 'y'
            default_port = 8883 if config['tls'] else 1883
            config['port'] = int(input(f'MQTT port [{default_port}]: ') or default_port)
        try:
            probe(config)
            return config
        except Rejected as error:
            print(str(error) + '. Default/existing credentials did not work.', file=sys.stderr)
            if not interactive:
                raise
            config['username'] = input('MQTT username (empty for anonymous): ').strip()
            config['password'] = getpass.getpass('MQTT password: ') if config['username'] else ''
        except (OSError, ValueError) as error:
            # Connection/certificate failures should not be mistaken for a bad password.
            print('MQTT endpoint/configuration check failed (' + type(error).__name__ + ').', file=sys.stderr)
            if not interactive:
                raise ValueError('Check broker address, port, TLS, topic and network; credentials are hidden') from None
            if input('Change broker address/port/TLS? [y/N]: ').strip().lower() != 'y':
                raise ValueError('MQTT setup cancelled') from None
            config['host'] = ''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text()) if args.config else {
            'host': os.environ.get('MQTT_HOST', ''), 'port': int(os.environ.get('MQTT_PORT', '1883')),
            'topic': os.environ.get('MQTT_TOPIC', 'sys/agents/+/metrics'),
            'username': os.environ.get('MQTT_USERNAME', ''), 'password': os.environ.get('MQTT_PASSWORD', ''),
            'tls': os.environ.get('MQTT_TLS', '').lower() in ('1', 'true', 'yes')}
        config = setup(config, sys.stdin.isatty())
        # O_EXCL avoids following an existing symlink; installers provide a fresh staging path.
        fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as output:
            json.dump(config, output)
            output.write('\n')
        print('PASS: MQTT connection and subscription verified; credentials saved privately.')
    except (OSError, ValueError, Rejected):
        sys.exit('MQTT setup failed; configuration was not saved. Credentials are not printed.')


if __name__ == '__main__':
    main()
