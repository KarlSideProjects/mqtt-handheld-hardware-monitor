"""Run on the development computer: native DRM selection and power failure checks."""
import ctypes as C
from unittest.mock import Mock, patch

from trimui_monitor import DRMConnector, DRMProperty, DRMResources, display_power


def fixture(types=(10, 16), property_name=b'DPMS'):
    identifiers = (C.c_uint32 * len(types))(*range(147, 147 + len(types)))
    resources = DRMResources(count_connectors=len(types), connectors=identifiers)
    props = (C.c_uint32 * 1)(9)
    connectors = {identifier: DRMConnector(connector_id=identifier, connector_type=kind,
                  connection=1, count_props=1, props=props) for identifier, kind in zip(identifiers, types)}
    prop = DRMProperty(prop_id=9, name=property_name)
    drm = Mock()
    drm.drmModeGetResources.return_value = C.pointer(resources)
    drm.drmModeGetConnector.side_effect = lambda fd, identifier: C.pointer(connectors[identifier])
    drm.drmModeGetProperty.return_value = C.pointer(prop)
    drm.drmModeConnectorSetProperty.return_value = 0
    return drm


for mode, value, state in [('off', 3, 'Off\n'), ('on', 0, 'On\n')]:
    drm = fixture()
    with patch('trimui_monitor.C.CDLL', return_value=drm), patch('trimui_monitor.os.open', return_value=77), \
            patch('trimui_monitor.os.close') as close, patch('trimui_monitor.Path.read_text', return_value=state):
        display_power(mode)
        # DP and DSI may both report connected; only the DSI connector may be changed.
        drm.drmModeConnectorSetProperty.assert_called_once_with(77, 148, 9, value)
        close.assert_called_once_with(77)
        assert drm.drmModeFreeConnector.call_count == 2
        drm.drmModeFreeResources.assert_called_once()

for drm, readback in [(fixture(types=(10,)), 'Off'), (fixture(types=(16, 16)), 'Off'),
                      (fixture(property_name=b'OTHER'), 'Off'), (fixture(), 'On')]:
    with patch('trimui_monitor.C.CDLL', return_value=drm), patch('trimui_monitor.os.open', return_value=77), \
            patch('trimui_monitor.os.close') as close, patch('trimui_monitor.Path.read_text', return_value=readback):
        try:
            display_power('off')
        except OSError:
            pass
        else:
            raise AssertionError('Missing/ambiguous DSI or failed DPMS readback was accepted')
        close.assert_called_once_with(77)
        drm.drmModeFreeResources.assert_called_once()

drm = fixture()
drm.drmModeConnectorSetProperty.return_value = -1
with patch('trimui_monitor.C.CDLL', return_value=drm), patch('trimui_monitor.os.open', return_value=77), \
        patch('trimui_monitor.os.close') as close, patch('trimui_monitor.Path.read_text') as read:
    try:
        display_power('off')
    except OSError:
        pass
    else:
        raise AssertionError('DRM power failure was ignored')
    read.assert_not_called()
    close.assert_called_once_with(77)
print('PASS: dynamic DSI/DPMS selection, connected DP excluded, readback/driver failures, resources closed')
