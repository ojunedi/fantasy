# local-only-web Specification

## Purpose
The web app serves only requests made on this machine to a loopback name,
however it was started.

<!-- trace-prefix: LOCALWEB -->

## Requirements

### Requirement: Only this machine is served

The app SHALL refuse, with 403 and a plain reason, every request that arrives
on a non-loopback address or whose `Host` is not `localhost`, `127.0.0.1` or
`::1` (any port). A refused request SHALL NOT reach any route. The check
SHALL be part of the app the factory builds.

Serves: AC-1, AC-2, AC-3, AC-4, AC-5

#### Scenario: LOCALWEB-01 — A request from the network is refused

- **GIVEN** the app started bound to every interface
- **WHEN** a request arrives on the machine's network address
- **THEN** the response is 403 with a reason saying the app only serves this machine
- **AND** no route runs

#### Scenario: LOCALWEB-02 — A foreign host name on loopback is refused

- **GIVEN** a request arriving on 127.0.0.1
- **WHEN** its `Host` is `evil.example:8000`
- **THEN** the response is 403
- **AND** no route runs

#### Scenario: LOCALWEB-03 — This machine is served as today

- **GIVEN** a request arriving on a loopback address
- **WHEN** its `Host` is `localhost:8000`, `127.0.0.1:8000` or `[::1]:8000`
- **THEN** it is served as before

#### Scenario: LOCALWEB-04 — Every refusal is logged

- **GIVEN** a refused request
- **WHEN** it is refused
- **THEN** standard error names the address and the host it arrived with
