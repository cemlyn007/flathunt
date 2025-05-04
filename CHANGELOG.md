# CHANGELOG


## v0.18.0 (2025-05-04)

### Features

- Do not fetch if already let agreed
  ([`db1bba4`](https://github.com/cemlyn007/flathunt/commit/db1bba4aa44527fa4bfccbb2dd6dc40f1b8db1b9))

- Filter on displayed floor size
  ([`a806964`](https://github.com/cemlyn007/flathunt/commit/a806964cef8ecc903d53dba58af91d0c7cb14f5d))


## v0.17.0 (2025-05-03)

### Bug Fixes

- Rightmove app
  ([`471ad7e`](https://github.com/cemlyn007/flathunt/commit/471ad7e7f620d99d98e32c48befc92d835cfe5aa))

### Features

- Multi-threaded property filtering & viewer
  ([`50c2505`](https://github.com/cemlyn007/flathunt/commit/50c250508f7e8a26b932f55bd1c65ddc7bb84e28))

### Refactoring

- Typing
  ([`ae1c5d3`](https://github.com/cemlyn007/flathunt/commit/ae1c5d33745b27a1695290717fc9c9ff0d2ae2a2))


## v0.16.0 (2025-04-30)

### Features

- Cached search app
  ([`3e23594`](https://github.com/cemlyn007/flathunt/commit/3e23594c6d19edc84989aa8c916a11f9071261de))

- Rate limit
  ([`cf79dca`](https://github.com/cemlyn007/flathunt/commit/cf79dcad97c135d1af49d2eb4ce85772e9a24c0d))


## v0.15.0 (2025-04-28)

### Features

- Price on picker
  ([`e402b79`](https://github.com/cemlyn007/flathunt/commit/e402b79ecf339477b0cc1f5de507b84e8b16fe72))

### Refactoring

- Remove incorrect comment
  ([`e8960cc`](https://github.com/cemlyn007/flathunt/commit/e8960cc3ba45c85e4930a5fabd5c40ba325981f8))


## v0.14.0 (2025-04-28)

### Features

- Display historical property data from disk ([#15](https://github.com/cemlyn007/flathunt/pull/15),
  [`ea48e6e`](https://github.com/cemlyn007/flathunt/commit/ea48e6e224f7352e7f5282ac900bcf4f7b3a55fa))


## v0.13.1 (2025-04-27)

### Bug Fixes

- Postcode sub district code
  ([`80f9189`](https://github.com/cemlyn007/flathunt/commit/80f91893fab79169092be9187f061bbffb521b0a))

### Testing

- Add postcode tests
  ([`19eff7e`](https://github.com/cemlyn007/flathunt/commit/19eff7e1ad5301495402bc6bf4a43201214f072e))


## v0.13.0 (2025-04-27)

### Bug Fixes

- Postcode parsing
  ([`bbf58b4`](https://github.com/cemlyn007/flathunt/commit/bbf58b46f4b4335931eab98f6efa2e97986464a6))

### Continuous Integration

- Relax pre-commit python minor
  ([`f9e041d`](https://github.com/cemlyn007/flathunt/commit/f9e041d6de4df4aa0cf09aaf07b869bc23f29707))

### Features

- Make search boundaries more generic to polylines
  ([`64f549e`](https://github.com/cemlyn007/flathunt/commit/64f549e579a6c769daabb784eefde3bfd9e61f9e))

- Support retry via tenacity
  ([`470e41a`](https://github.com/cemlyn007/flathunt/commit/470e41afc873b27f6b0eb7654d32b30402b3d0d4))


## v0.12.0 (2025-04-17)

### Features

- Store historical property data to disk ([#14](https://github.com/cemlyn007/flathunt/pull/14),
  [`ac10b0a`](https://github.com/cemlyn007/flathunt/commit/ac10b0a2ac25c48b5d863c4819db5260c3afa45e))

* feat: fetch script

* fix: fetch

* feat: search boundaries script


## v0.11.0 (2025-04-13)

### Features

- Support polyline rightmove search
  ([`44e693c`](https://github.com/cemlyn007/flathunt/commit/44e693c983d323b9895ebb8b5e4ab50e4d3066b3))


## v0.10.0 (2025-04-13)

### Features

- Generate postcode boundaries
  ([`f96f088`](https://github.com/cemlyn007/flathunt/commit/f96f08853c0bebbc7f201ac8e116c78bc084b06f))


## v0.9.2 (2025-04-13)

### Bug Fixes

- Update model attribute type signatures
  ([`c0a7081`](https://github.com/cemlyn007/flathunt/commit/c0a7081b6a1bbd9fefafe603aa550f2aa504d36c))

### Continuous Integration

- Ruff include jupyter notebooks
  ([`3f57ed0`](https://github.com/cemlyn007/flathunt/commit/3f57ed00df1eceb201cc6884ccabcd2fd492faa5))

### Refactoring

- Rightmove api
  ([`f76d927`](https://github.com/cemlyn007/flathunt/commit/f76d9272b275bb509075e4419eba27414a26bdd3))

- Test fix typing
  ([`19d58a5`](https://github.com/cemlyn007/flathunt/commit/19d58a59622f409e314f991eee7c0ce9c4d5f088))


## v0.9.1 (2025-04-12)

### Bug Fixes

- Cache model dump
  ([`4bbbce1`](https://github.com/cemlyn007/flathunt/commit/4bbbce1257f3dafa791644a2c649866cfa42449f))


## v0.9.0 (2025-04-12)

### Documentation

- Update readme
  ([`30bd898`](https://github.com/cemlyn007/flathunt/commit/30bd8986dc83ce90dc3b0206c42e32660c002d92))

### Features

- Rightmove search historical properties ([#10](https://github.com/cemlyn007/flathunt/pull/10),
  [`16d7a47`](https://github.com/cemlyn007/flathunt/commit/16d7a478eb4c3ab7b8bcf810ee54fc8fe4c3f2ee))

### Testing

- Refactor and fix tests
  ([`da869f5`](https://github.com/cemlyn007/flathunt/commit/da869f5da5c568327e2ccc1d8a3a4cfb75e23f48))

- Refactor and fix tests
  ([`97a1cfa`](https://github.com/cemlyn007/flathunt/commit/97a1cfaa0f12a3df48776afc485e203cac8b5f72))

- Serialization of property models
  ([`439ce02`](https://github.com/cemlyn007/flathunt/commit/439ce025fd24769d47dbb3c7f84714dc95f9cd19))


## v0.8.0 (2025-04-06)

### Features

- Rename repository to flathunt
  ([`fee2622`](https://github.com/cemlyn007/flathunt/commit/fee2622ef8fb8be4fcdf028fbe9d83155ba63328))


## v0.7.0 (2025-04-06)

### Bug Fixes

- Handling of timezone with tfl api
  ([`7aff023`](https://github.com/cemlyn007/flathunt/commit/7aff023e73e7965e9e41f1af9c2928f44755b1d6))

### Features

- Add lookup models
  ([`1b905e8`](https://github.com/cemlyn007/flathunt/commit/1b905e8f171d3d119f8388634a10661af14855df))

- Add rightmove pydantic models
  ([`126ecbf`](https://github.com/cemlyn007/flathunt/commit/126ecbf46112389177a10e0015574e3509ee756e))

- Flathunt search with tfl journey
  ([`3140924`](https://github.com/cemlyn007/flathunt/commit/3140924cd8f3339e2b0d63d8e32cb680d66178cf))

- Stronger typing
  ([`44be0de`](https://github.com/cemlyn007/flathunt/commit/44be0de7a7e39d6caf97701d473623280f82917c))

- Support python 3.9
  ([`44f4a27`](https://github.com/cemlyn007/flathunt/commit/44f4a271f5729888dcc18f24c434031601b237ed))

- Support python 3.9
  ([`3f94e06`](https://github.com/cemlyn007/flathunt/commit/3f94e06b8f04bfa92e91b236db3007dfc72fa47a))

- Support python 3.9
  ([`68ffb7d`](https://github.com/cemlyn007/flathunt/commit/68ffb7d66891747c028ead3ef79ea212de21269d))

- Support python 3.9
  ([`8040845`](https://github.com/cemlyn007/flathunt/commit/80408452113bca113567c2cd10917c38bdc950c6))


## v0.6.0 (2025-03-31)

### Bug Fixes

- `get_journey_options` when arrival datetime is not None
  ([`0d93ab7`](https://github.com/cemlyn007/flathunt/commit/0d93ab724e0d67bccb4436f394d329a411b701c2))

- Rightmove api search when 1000 or more results
  ([`ed83658`](https://github.com/cemlyn007/flathunt/commit/ed8365844fed052a80b26e847047f7edfe4762f7))

### Features

- Improve types for `get_journey`
  ([`6c05eb6`](https://github.com/cemlyn007/flathunt/commit/6c05eb63fde2687ec60f2b286233697cca47ae7c))

- Make tfl api more generic
  ([`97bd6bc`](https://github.com/cemlyn007/flathunt/commit/97bd6bcc1b00d1490588700950f56c920d50f037))

- Tfl api
  ([`9e8cc54`](https://github.com/cemlyn007/flathunt/commit/9e8cc544ec2b90f89a2ca8f29a00a369f6f47204))

### Refactoring

- Clean up signature
  ([`32bb34d`](https://github.com/cemlyn007/flathunt/commit/32bb34da5e228f92d034278f35bb7b11122f0b71))

- Move rightmove into src
  ([`fc2692c`](https://github.com/cemlyn007/flathunt/commit/fc2692c320627efc20f702c2ef22f124209b89fc))


## v0.5.0 (2025-03-30)

### Continuous Integration

- Remove pytest as it is run by pre-commit
  ([`8690bdf`](https://github.com/cemlyn007/flathunt/commit/8690bdf08fbf0c2983e63d06ddac61bad89c227c))

### Features

- `update-search-locations` script
  ([`f0543a6`](https://github.com/cemlyn007/flathunt/commit/f0543a640c7f25e25774c6c4fd716005517858e3))

- Make cache optional
  ([`5f14cd9`](https://github.com/cemlyn007/flathunt/commit/5f14cd9aaf45268d6fcb8b81c142ac4dd86317b6))

- Search script uses search locations JSON file
  ([`4cceb7f`](https://github.com/cemlyn007/flathunt/commit/4cceb7fd7c56c049c630c8c694fd88f161a7b984))

- Update search locations preserves order of original file
  ([`4d59bde`](https://github.com/cemlyn007/flathunt/commit/4d59bdeaec33e621f753c869ad6e73acd6ed346a))


## v0.4.1 (2025-03-30)

### Bug Fixes

- Release with correct version
  ([`4c8b669`](https://github.com/cemlyn007/flathunt/commit/4c8b6695d86fa6a58df77c1b04c2cbe736d66498))

### Continuous Integration

- Pre-commit hook to run pytest
  ([`a60f07b`](https://github.com/cemlyn007/flathunt/commit/a60f07bd79d673927989b3c2ff4ae64319f1f787))


## v0.4.0 (2025-03-30)

### Continuous Integration

- Run semantic-release version before publish
  ([`43d2044`](https://github.com/cemlyn007/flathunt/commit/43d20449fd4fdd3fd55749f69ba31df7fafd40b7))

### Features

- `get_map_url`
  ([`d8f6b29`](https://github.com/cemlyn007/flathunt/commit/d8f6b29801b25a28bed3b2e217d7aea8fc4d82d2))


## v0.3.0 (2025-03-30)

### Bug Fixes

- `rightmove.property_url` to return https
  ([`8fd86b9`](https://github.com/cemlyn007/flathunt/commit/8fd86b957ff07c15a564adcbee12c496aafeeba7))

### Continuous Integration

- Python-package semantic-release verbosity
  ([`ec0bd66`](https://github.com/cemlyn007/flathunt/commit/ec0bd66598638a77491c4673b985c1ab186a5f96))

- Remove poetry
  ([`aea9c1c`](https://github.com/cemlyn007/flathunt/commit/aea9c1c4db632508e46622acf77eb91e85b27ab7))

- Switch to conventional commit parser
  ([`94f0db2`](https://github.com/cemlyn007/flathunt/commit/94f0db2c36c54380dcfc9a466511a238aec57572))

- Use ruff in pre-commit
  ([`434f569`](https://github.com/cemlyn007/flathunt/commit/434f5690542caca4a36f9a493ee56a3890e9ace4))

### Features

- Better logic for when to wait for user to want to continue
  ([`e75295a`](https://github.com/cemlyn007/flathunt/commit/e75295a392be1311a659474e293c10c067224a01))

- Package search cli into package
  ([`f3b6f00`](https://github.com/cemlyn007/flathunt/commit/f3b6f007bbdb3b1b6e870873d8d31e2dc7ef0cca))

- Search script terminate without stack trace when keyboard interrupt
  ([`606ac42`](https://github.com/cemlyn007/flathunt/commit/606ac42f4414a4169440d615a997cfe23a24cc5b))

- Use http instead of requests
  ([`d134355`](https://github.com/cemlyn007/flathunt/commit/d13435546635426f59a3e12682c4c5ab8a14ea56))

### Refactoring

- Rename protected method
  ([`4d96e99`](https://github.com/cemlyn007/flathunt/commit/4d96e9941ee26f493aa2fcef7d4d98fea8e3fc4d))


## v0.2.0 (2023-08-05)

### Continuous Integration

- Keep `python-semantic-release` less than major 8
  ([`5ca96bc`](https://github.com/cemlyn007/flathunt/commit/5ca96bc225ca52dc162e77d8368bf2a0f0e9d92b))

### Features

- Example search script
  ([`37f71f8`](https://github.com/cemlyn007/flathunt/commit/37f71f8c3709e6b212b1d5b46e1d51250111dc58))


## v0.1.1 (2023-05-22)

### Bug Fixes

- Wrong argument in `input` in `App.search`
  ([`79652f1`](https://github.com/cemlyn007/flathunt/commit/79652f10d81908a9328cdc4e102a1867672fc02e))


## v0.1.0 (2023-05-20)

### Features

- Initial commit
  ([`42f11af`](https://github.com/cemlyn007/flathunt/commit/42f11af4f40ddc55e94b6338a57a045d18d74c33))
