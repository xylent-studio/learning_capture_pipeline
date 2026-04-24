# 14 Autonomous Data Model Addendum

## permission_manifest

Represents contract/vendor permission scope.

Fields:

- permission_manifest_id
- permission_basis
- contract_reference
- effective_date
- expires_at
- source_platform
- source_base_url
- default_rights_status
- ai_use_allowed
- derivative_use_allowed
- internal_training_use_allowed
- screen_capture_allowed
- visible_dom_capture_allowed
- audio_capture_allowed
- video_capture_allowed
- quiz_capture_allowed
- report_capture_allowed
- allowed_accounts
- allowed_vendors
- allowed_course_patterns
- excluded_paths
- pii_policy
- notes

## course_inventory_item

A visible-UI-discovered course candidate.

Fields:

- inventory_item_id
- source_url
- visible_title
- visible_description
- brand
- vendor
- jurisdiction
- visible_status
- estimated_duration
- discovered_at
- discovery_screenshot_uri
- permission_status
- capture_priority

## course_capture_plan

A concrete plan generated before capture.

Fields:

- plan_id
- inventory_item_id
- course_url
- course_title
- expected_lessons
- expected_duration_minutes
- capture_mode
- recorder_profile
- screenshot_interval_seconds
- max_course_minutes
- quiz_capture_mode
- qa_thresholds
- status

## autonomous_run

A scheduler/execution record.

Fields:

- run_id
- capture_batch_id
- plan_id
- runner_version
- auth_state_alias
- started_at
- ended_at
- status
- final_state
- failure_reason
- qa_report_id

## page_observation

The bot's model of each UI state.

Fields:

- observation_id
- run_id
- capture_session_id
- timestamp_ms
- url
- page_title
- page_kind
- visible_text_sample
- visible_buttons
- visible_links
- media_summary
- screenshot_uri
- confidence

## navigation_decision

The action selected from an observation.

Fields:

- decision_id
- observation_id
- action
- selector_strategy
- target_label
- confidence
- reason
- result_status
- result_notes
