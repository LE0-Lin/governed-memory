package governed_memory

import rego.v1

default allow := false

operator if {
	input.role in {"admin", "approver"}
	is_boolean(input.protected)
	is_boolean(input.source_revoked)
	is_string(input.state)
}

protection_ok if not input.protected
protection_ok if input.role == "admin"

allow if {
	operator
	protection_ok
	input.action == "withdraw_source"
}

allow if {
	operator
	protection_ok
	input.action in {"approve", "approve_support"}
	input.state == "proposed"
	not input.source_revoked
}

allow if {
	operator
	protection_ok
	input.action == "reject"
	input.state == "proposed"
}

allow if {
	operator
	protection_ok
	input.action == "revoke"
	input.state in {"active", "superseded"}
}
