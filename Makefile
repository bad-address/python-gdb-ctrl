.PHONY: all test coverage dist upload clean doc deps

all:
	@echo "Usage: make deps[-dev]"
	@echo " - deps: install the dependencies for using gdb_mi"
	@echo " - deps-dev: install the dependencies for using and build gdb_mi"
	@echo
	@echo "Usage: make test"
	@echo "Run the suite of tests using the gdb installed locally."
	@echo
	@echo "Usage: make dist|upload"
	@echo "Package python-gdb-mi (dist) and upload it to pypi (upload)"
	@echo
	@echo "Usage: make format[-test]"
	@echo "Format the source code following the PEP 8 style."
	@echo "Use format-test to verify the complaince without touching"
	@echo "the code"
	@echo
	@echo "Usage: make coverage"
	@echo "Run several times variants of 'make test' with the coverage"
	@echo "activated and show the results."
	@echo
	@echo "Usage: make clean|clean_test"
	@echo "Clean the environment in general (clean) or only related"
	@echo "with the environment for testing (clean_test)."
	@exit 1


deps:
	pip3 install -e .

deps-dev: deps
	pip3 install -r requirements-dev.txt

test:
	@byexample -l python --ff --timeout 6 -- README.md


## Formatting
#  ==========
format:
	yapf -vv -i --style=.style.yapf --recursive gdb_ctrl/

format-test:
	yapf -vv --style=.style.yapf --diff --recursive gdb_ctrl/
#
##

## Packaging and clean up
#  ======================

dist:
	rm -Rf dist/ build/ *.egg-info
	python3 setup.py sdist bdist_wheel
	rm -Rf build/ *.egg-info

upload: dist
	twine upload dist/*.tar.gz dist/*.whl

clean:
	rm -Rf dist/ build/ *.egg-info
	rm -Rf build/ *.egg-info
	find . -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	rm -f README.rst

#
##
