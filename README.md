[![CircleCI build status](https://circleci.com/gh/derpston/me7.svg?style=shield&circle-token=9b29247acf08a7580765d603e68b71af44f66a8b)](https://circleci.com/gh/derpston/me7)
# me7

Python library for interacting with [Bosch ME7](http://s4wiki.com/wiki/Bosch_ME7.1) [ECU](https://en.wikipedia.org/wiki/Engine_control_unit)s, common in many [VAG](https://en.wikipedia.org/wiki/Volkswagen_Group) cars from the late 1990s to the early 2000s.

This implements a small subset of the [KWP2000/ISO-14230](https://en.wikipedia.org/wiki/Keyword_Protocol_2000) protocol.

## Status

Undergoing significant refactor, don't use this yet.

## Known deficiencies

* We require libftdi to be installed for testing because of incomplete and awkward mocking in some of the tests.

