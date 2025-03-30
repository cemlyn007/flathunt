# CHANGELOG


## v0.5.0 (2025-03-30)

### Continuous Integration

- Remove pytest as it is run by pre-commit
  ([`8690bdf`](https://github.com/cemlyn007/rightmove/commit/8690bdf08fbf0c2983e63d06ddac61bad89c227c))

### Features

- `update-search-locations` script
  ([`f0543a6`](https://github.com/cemlyn007/rightmove/commit/f0543a640c7f25e25774c6c4fd716005517858e3))

- Make cache optional
  ([`5f14cd9`](https://github.com/cemlyn007/rightmove/commit/5f14cd9aaf45268d6fcb8b81c142ac4dd86317b6))

- Search script uses search locations JSON file
  ([`4cceb7f`](https://github.com/cemlyn007/rightmove/commit/4cceb7fd7c56c049c630c8c694fd88f161a7b984))

- Update search locations preserves order of original file
  ([`4d59bde`](https://github.com/cemlyn007/rightmove/commit/4d59bdeaec33e621f753c869ad6e73acd6ed346a))


## v0.4.1 (2025-03-30)

### Bug Fixes

- Release with correct version
  ([`4c8b669`](https://github.com/cemlyn007/rightmove/commit/4c8b6695d86fa6a58df77c1b04c2cbe736d66498))

### Continuous Integration

- Pre-commit hook to run pytest
  ([`a60f07b`](https://github.com/cemlyn007/rightmove/commit/a60f07bd79d673927989b3c2ff4ae64319f1f787))


## v0.4.0 (2025-03-30)

### Continuous Integration

- Run semantic-release version before publish
  ([`43d2044`](https://github.com/cemlyn007/rightmove/commit/43d20449fd4fdd3fd55749f69ba31df7fafd40b7))

### Features

- `get_map_url`
  ([`d8f6b29`](https://github.com/cemlyn007/rightmove/commit/d8f6b29801b25a28bed3b2e217d7aea8fc4d82d2))


## v0.3.0 (2025-03-30)

### Bug Fixes

- `rightmove.property_url` to return https
  ([`8fd86b9`](https://github.com/cemlyn007/rightmove/commit/8fd86b957ff07c15a564adcbee12c496aafeeba7))

### Continuous Integration

- Python-package semantic-release verbosity
  ([`ec0bd66`](https://github.com/cemlyn007/rightmove/commit/ec0bd66598638a77491c4673b985c1ab186a5f96))

- Remove poetry
  ([`aea9c1c`](https://github.com/cemlyn007/rightmove/commit/aea9c1c4db632508e46622acf77eb91e85b27ab7))

- Switch to conventional commit parser
  ([`94f0db2`](https://github.com/cemlyn007/rightmove/commit/94f0db2c36c54380dcfc9a466511a238aec57572))

- Use ruff in pre-commit
  ([`434f569`](https://github.com/cemlyn007/rightmove/commit/434f5690542caca4a36f9a493ee56a3890e9ace4))

### Features

- Better logic for when to wait for user to want to continue
  ([`e75295a`](https://github.com/cemlyn007/rightmove/commit/e75295a392be1311a659474e293c10c067224a01))

- Package search cli into package
  ([`f3b6f00`](https://github.com/cemlyn007/rightmove/commit/f3b6f007bbdb3b1b6e870873d8d31e2dc7ef0cca))

- Search script terminate without stack trace when keyboard interrupt
  ([`606ac42`](https://github.com/cemlyn007/rightmove/commit/606ac42f4414a4169440d615a997cfe23a24cc5b))

- Use http instead of requests
  ([`d134355`](https://github.com/cemlyn007/rightmove/commit/d13435546635426f59a3e12682c4c5ab8a14ea56))

### Refactoring

- Rename protected method
  ([`4d96e99`](https://github.com/cemlyn007/rightmove/commit/4d96e9941ee26f493aa2fcef7d4d98fea8e3fc4d))


## v0.2.0 (2023-08-05)

### Continuous Integration

- Keep `python-semantic-release` less than major 8
  ([`5ca96bc`](https://github.com/cemlyn007/rightmove/commit/5ca96bc225ca52dc162e77d8368bf2a0f0e9d92b))

### Features

- Example search script
  ([`37f71f8`](https://github.com/cemlyn007/rightmove/commit/37f71f8c3709e6b212b1d5b46e1d51250111dc58))


## v0.1.1 (2023-05-22)

### Bug Fixes

- Wrong argument in `input` in `App.search`
  ([`79652f1`](https://github.com/cemlyn007/rightmove/commit/79652f10d81908a9328cdc4e102a1867672fc02e))


## v0.1.0 (2023-05-20)

### Features

- Initial commit
  ([`42f11af`](https://github.com/cemlyn007/rightmove/commit/42f11af4f40ddc55e94b6338a57a045d18d74c33))
