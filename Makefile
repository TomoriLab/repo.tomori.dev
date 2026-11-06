# SPDX-License-Identifier: AGPL-3.0-only
.PHONY: build site sign verify publish deploy

build:
	python3 scripts/build-repository.py $(if $(ARTIFACTS),--artifacts '$(ARTIFACTS)')

site:
	python3 scripts/site_renderer.py

sign:
	./scripts/sign-repository.sh

verify:
	python3 scripts/verify-repository.py

publish:
	$(MAKE) build
	$(MAKE) sign
	$(MAKE) verify

deploy: verify
	python3 scripts/deploy.py
