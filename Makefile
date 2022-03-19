
test-examples:
	python libido.py examples -p
test-self:
	python libido.py libido.py -p
test-all:
	python libido.py . -p -i venv/ --collect-only


fullrelease:
	echo -e "\n\n\n\n\n\n\nn\n\n\n\n" | fullrelease
