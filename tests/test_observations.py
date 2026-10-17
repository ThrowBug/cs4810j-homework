from agents.my_agent import compare_observations
from harness.tasks import Task


def test_recently_viewed_waits_for_return_to_dashboard():
	task = Task('recently_viewed_book', 'Recently Viewed Book', ())
	initial = {'path': '/', 'recent': ['Shelf', 'Book2', 'Chapter 2']}
	book = {'path': '/books/book2', 'heading': 'Book2', 'book_entries': []}
	observations = [initial, dict(initial), book]

	assert compare_observations(task, observations) is None

	observations.append({'path': '/', 'recent': ['Book2', 'Shelf']})
	verdict = compare_observations(task, observations)
	assert verdict is not None
	assert not verdict.passed


def test_create_book_waits_for_saved_book_and_final_listing():
	task = Task('create_book', 'Create Book', ())
	initial = {'path': '/books', 'book_cards': [{'name': 'Book', 'description': 'Description'}]}
	form = {'path': '/create-book', 'form_name': 'New Book', 'form_description': 'New Book Description'}
	book = {'path': '/books/new-book', 'heading': 'New Book', 'book_entries': []}
	observations = [initial, dict(initial), form]

	assert compare_observations(task, observations) is None
	observations.append(book)
	assert compare_observations(task, observations) is None

	observations.append({'path': '/books', 'book_cards': [
		{'name': 'Book', 'description': 'Description'},
		{'name': 'New Book', 'description': 'New Book Description'},
	]})
	verdict = compare_observations(task, observations)
	assert verdict is not None
	assert verdict.passed
