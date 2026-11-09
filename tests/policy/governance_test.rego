package governed_memory_test

import data.governed_memory
import rego.v1

review := {
	"role": "approver", "action": "approve", "state": "proposed",
	"protected": false, "source_revoked": false,
}

test_operator_can_approve if governed_memory.allow with input as review

test_agent_cannot_self_approve if {
	not governed_memory.allow with input as object.union(review, {"role": "agent"})
}

test_protected_fact_needs_admin if {
	not governed_memory.allow with input as object.union(review, {"protected": true})
	governed_memory.allow with input as object.union(review, {"protected": true, "role": "admin"})
}

test_withdrawn_source_cannot_be_approved if {
	not governed_memory.allow with input as object.union(review, {"source_revoked": true})
}

test_terminal_state_cannot_be_reactivated if {
	every state in ["rejected", "revoked", "superseded"] {
		not governed_memory.allow with input as object.union(review, {"state": state})
	}
}

test_superseded_candidate_can_be_revoked if {
	governed_memory.allow with input as object.union(review, {"action": "revoke", "state": "superseded"})
}

test_rejecting_a_withdrawn_source_is_allowed if {
	governed_memory.allow with input as object.union(review, {"action": "reject", "source_revoked": true})
}

test_protected_source_withdrawal_needs_admin if {
	request := object.union(review, {"action": "withdraw_source", "protected": true})
	not governed_memory.allow with input as request
	governed_memory.allow with input as object.union(request, {"role": "admin"})
}

test_missing_identity_is_denied if not governed_memory.allow with input as {}

test_missing_protection_fields_are_denied if {
	not governed_memory.allow with input as object.remove(review, {"protected"})
	not governed_memory.allow with input as object.remove(review, {"source_revoked"})
}
