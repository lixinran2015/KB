from packages.engines.trigger_engine import TriggerStateMachine


def test_state_machine_transitions():
    sm = TriggerStateMachine()
    assert sm.state == "watching"

    sm.trigger()
    assert sm.state == "triggered"

    sm.confirm()
    assert sm.state == "confirmed"


def test_invalid_transition():
    sm = TriggerStateMachine()
    assert sm.state == "watching"

    # Cannot confirm from watching
    sm.confirm()
    assert sm.state == "watching"


def test_expire_transition():
    sm = TriggerStateMachine()
    sm.trigger()
    assert sm.state == "triggered"

    sm.expire()
    assert sm.state == "expired"
