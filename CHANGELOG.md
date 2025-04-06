# CHANGELOG


## v0.7.0 (2025-04-06)

### Bug Fixes

- Handling of timezone with tfl api
  ([`7aff023`](https://github.com/cemlyn007/rightmove/commit/7aff023e73e7965e9e41f1af9c2928f44755b1d6))

### Features

- Add lookup models
  ([`1b905e8`](https://github.com/cemlyn007/rightmove/commit/1b905e8f171d3d119f8388634a10661af14855df))

- Add rightmove pydantic models
  ([`126ecbf`](https://github.com/cemlyn007/rightmove/commit/126ecbf46112389177a10e0015574e3509ee756e))

- Flathunt search with tfl journey
  ([`3140924`](https://github.com/cemlyn007/rightmove/commit/3140924cd8f3339e2b0d63d8e32cb680d66178cf))

- Stronger typing
  ([`44be0de`](https://github.com/cemlyn007/rightmove/commit/44be0de7a7e39d6caf97701d473623280f82917c))

- Support python 3.9
  ([`44f4a27`](https://github.com/cemlyn007/rightmove/commit/44f4a271f5729888dcc18f24c434031601b237ed))

- Support python 3.9
  ([`3f94e06`](https://github.com/cemlyn007/rightmove/commit/3f94e06b8f04bfa92e91b236db3007dfc72fa47a))

- Support python 3.9
  ([`68ffb7d`](https://github.com/cemlyn007/rightmove/commit/68ffb7d66891747c028ead3ef79ea212de21269d))

- Support python 3.9
  ([`8040845`](https://github.com/cemlyn007/rightmove/commit/80408452113bca113567c2cd10917c38bdc950c6))


## v0.6.0 (2025-03-31)

### Bug Fixes

- `get_journey_options` when arrival datetime is not None
  ([`0d93ab7`](https://github.com/cemlyn007/rightmove/commit/0d93ab724e0d67bccb4436f394d329a411b701c2))

- Rightmove api search when 1000 or more results
  ([`ed83658`](https://github.com/cemlyn007/rightmove/commit/ed8365844fed052a80b26e847047f7edfe4762f7))

### Features

- Improve types for `get_journey`
  ([`6c05eb6`](https://github.com/cemlyn007/rightmove/commit/6c05eb63fde2687ec60f2b286233697cca47ae7c))

- Make tfl api more generic
  ([`97bd6bc`](https://github.com/cemlyn007/rightmove/commit/97bd6bcc1b00d1490588700950f56c920d50f037))

- Tfl api
  ([`9e8cc54`](https://github.com/cemlyn007/rightmove/commit/9e8cc544ec2b90f89a2ca8f29a00a369f6f47204))

### Refactoring

- Clean up signature
  ([`32bb34d`](https://github.com/cemlyn007/rightmove/commit/32bb34da5e228f92d034278f35bb7b11122f0b71))

- Move rightmove into src
  ([`fc2692c`](https://github.com/cemlyn007/rightmove/commit/fc2692c320627efc20f702c2ef22f124209b89fc))


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
