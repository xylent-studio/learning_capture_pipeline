.PHONY: test compile validate

test:
	pytest

compile:
	python -m compileall src

validate: compile test
