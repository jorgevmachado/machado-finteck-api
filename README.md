[![GitHub stars][githubStar-img]][githubStar-url]
[![GitHub forks][githubForks-img]][githubForks-url]
[![GitHub issues][githubIssues-img]][githubIssues-url]
[![GitHub license][githubLicense-img]][githubLicense-url]
[![LinkedIn][linkedin-shield]][linkedin-url]

<!-- TABLE OF CONTENTS -->
<details>
  <summary>Table of Contents</summary>
  <ol>
    <li>
        <a href="#overview">Overview</a>
    </li>
    <li>
      <a href="#about-the-project">About The Project</a>
      <ul>
        <li><a href="#built-with">Built With</a></li>
        <li><a href="#architecture">Architecture</a></li>
      </ul>
    </li>
    <li>
      <a href="#getting-started">Getting Started</a>
      <ul>
        <li><a href="#prerequisites">Prerequisites</a></li>
        <li><a href="#installation">Installation</a></li>
      </ul>
    </li>
    <li><a href="#usage">Usage</a></li>
    <li><a href="#roadmap">Roadmap</a></li>
    <li><a href="#contributing">Contributing</a></li>
    <li><a href="#technical-decisions">Technical Decisions</a></li>
     <li><a href="#api-route-map">API Route Map</a></li>
    <li><a href="#license">License</a></li>
    <li><a href="#contact">Contact</a></li>
    <li><a href="#acknowledgments">Acknowledgments</a></li>
  </ol>
</details>

<!-- OVERVIEW -->
<a id="overview"></a>
## 🚀 Overview
RESTful API, built with FastAPI and async SQLAlchemy.

Includes JWT authentication, pagination, caching support, and a layered architecture (domain, service, repository) designed for scalability and maintainability.

<!-- ABOUT THE PROJECT -->
## About The Project

The project was built with FastAPI, async SQLAlchemy, and domain-driven architecture, keeping clear responsibilities between routes, services, repositories, and schemas.

Main points:
- Domain structure: each feature lives in `app/domain/<feature>` with route, service, repository, and schema layers.
- Async persistence: async SQLAlchemy with engine configured in `app/core/database.py`.
- Settings: environment variables via Pydantic Settings in `app/core/settings.py`.
- Authentication: JWT with password hashing using `pwdlib[argon2]`.
- Migrations: Alembic for database versioning in `migrations/`.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- ARCHITECTURE -->
## Architecture

The project follows a clean, domain-driven architecture to ensure maintainability, scalability, and clear separation of concerns. Each feature is organized into its own domain module under `app/domain/<feature>`, containing:

- **Routes**: Define the API endpoints and handle HTTP requests.
- **Services**: Act as orchestrators, coordinating requests and integrating operations across Business, Repository, and Schema layers. They may contain application-level logic, while core business rules are encapsulated in the Business layer.
- **Business**: Encapsulate the core business rules and domain logic. All critical validations, calculations, and domain-specific rules are implemented here, ensuring the integrity and consistency of the application's behavior.
- **Repositories**: Abstract data access and persistence, using async SQLAlchemy for efficient I/O operations.
- **Schemas**: Define data validation and serialization using Pydantic models.

**Core modules** (in `app/core/`) provide shared infrastructure, such as database configuration, authentication, and settings management. The use of async SQLAlchemy and FastAPI enables high performance and non-blocking request handling, making the API suitable for production environments with high concurrency.

**Key architectural decisions:**
- Domain isolation: Each feature is self-contained, making it easy to extend or refactor.
- Async-first: All database and I/O operations are asynchronous for maximum throughput.
- Environment-driven configuration: All settings are managed via environment variables and Pydantic Settings for flexibility and security.
- JWT authentication: Secure user authentication and authorization.
- Alembic migrations: Reliable and versioned database schema management.
- Caching layer (Redis): Designed to support low-latency reads for high-frequency queries.

This architecture is inspired by best practices from enterprise backend systems, ensuring the project is both educational and ready for real-world use.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- API ROUTE MAP -->
## API Route Map

Below is a summary of the main API routes for each service, with a brief explanation of their purpose:

### Auth Service
- `POST /auth/login` — Authenticate user and return JWT token
- `POST /auth/register` — Register a new user

> For a complete list and details of all endpoints, see the interactive API docs at `/docs` after running the project.
<p align="right">(<a href="#readme-top">back to top</a>)</p>


<!-- TECHNICAL DECISIONS -->
## Technical Decisions

This project was developed with a focus on performance, maintainability, and real-world applicability. Key decisions include:

- **FastAPI**: Chosen for its high performance, async support, and automatic OpenAPI documentation.
- **Async SQLAlchemy**: Enables efficient handling of I/O-bound operations and high concurrency.
- **Alembic**: Provides robust database migrations and version control.
- **Pydantic Settings**: Simplifies environment-based configuration and validation.
- **Passlib (argon2)**: Secure password hashing for user authentication.
- **PyJWT**: Industry-standard JWT token management for stateless authentication.
- **FastAPI Pagination**: Native, efficient pagination for large datasets.
- **aiosqlite/psycopg**: Async drivers for SQLite and PostgreSQL, supporting both development and production databases.
- **tzdata**: Ensures correct timezone handling across environments.

These choices were made to balance developer experience, security, and scalability, making the project a strong foundation for any backend system that requires robust data management and user authentication.

<p align="right">(<a href="#readme-top">back to top</a>)</p>

### Built With

Main libraries and tools used:

* [![Poetry][Poetry]][Poetry-url] - Python dependency and environment manager
* [![FastAPI][FastAPI]][FastAPI-url] - Asynchronous web framework
* [![SQLAlchemy][sqlalchemy]][sqlalchemy-url] - Async ORM for persistence
* [![Alembic][Alembic]][Alembic-url] - Database migrations
* [![Pydantic][Pydantic]][Pydantic-url] Settings - Configuration via `.env`
* [![Passlib][Passlib]][Passlib-url] (pwdlib[argon2]) - Password hashing
* [![PyJWT][PyJWT]][PyJWT-url] - JWT tokens
* [![FastAPI Pagination][FastAPIPagination]][FastAPIPagination-url] - Native pagination
* [![aiosqlite][aiosqlite]][aiosqlite-url] / [![psycopg][psycopg]][psycopg-url] - Drivers for SQLite and PostgreSQL
* [![tzdata][tzdata]][tzdata-url] - Timezone support

Development tools:
- pytest, pytest-asyncio, pytest-cov: tests
- factory-boy, freezegun: fixtures and controlled dates
- testcontainers: ephemeral databases for tests
- ruff: lint and format

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- GETTING STARTED -->
## Getting Started

To run the project locally, follow the steps below to set up the environment, install dependencies, and start the API.

### Prerequisites

1. Python 3.13
2. Poetry installed ([documentation](https://python-poetry.org/docs/))
3. SQLite database (default) or PostgreSQL (optional)
4. It is recommended to create a `.env` file at the root with the variables:
   ```env
   ALGORITHM=HS256
   SECRET_KEY=change-me
   DATABASE_URL=sqlite+aiosqlite:///./dev.db
   ACCESS_TOKEN_EXPIRE_MINUTES=30
   ```
   For PostgreSQL:
   ```env
   DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/machadoFintech
   ```
### Installation

You can use the Makefile to simplify setup and common tasks:

- Install dependencies and activate environment:
  ```bash
  make install
  ```
- Run database migrations:
  ```bash
  make migrate
  ```
- Start the API:
  ```bash
  make run
  ```
- Run tests:
  ```bash
  make test
  ```
- Lint and format:
  ```bash
  make lint
  make format
  ```

Or, if you prefer, follow the manual steps below:

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/machado-fintech-api.git
   cd machado-fintech-api
   ```
2. Install dependencies and activate the environment:
   ```bash
   poetry env use 3.13
   poetry install
   poetry shell
   ```
3. Run database migrations:
   ```bash
   alembic upgrade head
   ```
4. Start the API:
   ```bash
   fastapi dev app/main.py
   ```
   The API will be available at `http://localhost:8000` and the documentation at:
   - `http://localhost:8000/docs`
   - `http://localhost:8000/redoc`

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- USAGE EXAMPLES -->
## Usage

Usage example:

You can also use the Makefile for common tasks:

- Run the API:
  ```bash
  make run
  ```
- Run tests:
  ```bash
  make test
  ```
- Lint and format:
  ```bash
  make lint
  make format
  ```

Or manually:

1. Make requests to the API endpoints to create, list, update, or delete pokémons, trainers, and battles.
2. Use the interactive documentation at `/docs` to explore and test the endpoints.

To run the tests:
```bash
pytest -v
```

For lint and formatting:
```bash
ruff check .
ruff format .
```

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- ROADMAP -->
## Roadmap

- [x] Domain structure
- [] Async persistence
- [] JWT authentication
- [] Native pagination
- [] Alembic migrations
- [] Automated tests
- [] Lint and format

See the [open issues](https://github.com/yourusername/machado-fintech-api/issues) for the full list of proposed features and known issues.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- CONTRIBUTING -->
## Contributing

Contributions are welcome! Follow the steps below to collaborate:

1. Fork the project
2. Create your feature branch (`git checkout -b feature/FeatureName`)
3. Commit your changes (`git commit -m 'feat: Feature description'`)
4. Push to the branch (`git push origin feature/FeatureName`)
5. Open a Pull Request

Suggestions for improvements can also be opened as issues with the tag "enhancement".
Don't forget to star the project!

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- LICENSE -->
## License

This project is licensed under the MIT License. You must give appropriate credit to the author (Jorge Machado) in any use, distribution, or derivative work.

See the [LICENSE](./LICENSE) file for details.

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- CONTACT -->
## Contact

Jorge Machado - jorge.vmachado@gmail.com

Project Link: [https://github.com/yourusername/machado-fintech-api](https://github.com/yourusername/machado-fintech-api)

<p align="right">(<a href="#readme-top">back to top</a>)</p>



<!-- ACKNOWLEDGMENTS -->
## Acknowledgments

Use this space to list resources you find helpful and would like to give credit to. I've included a few of my favorites to kick things off!

* [PokeAPI](https://pokeapi.co/)
* [Img Shields](https://shields.io)

<p align="right">(<a href="#readme-top">back to top</a>)</p>

<!-- MARKDOWN LINKS & IMAGES -->
[linkedin-shield]: https://img.shields.io/badge/-LinkedIn-black.svg?style=for-the-badge&logo=linkedin&colorB=555
[linkedin-url]: https://linkedin.com/in/yourusername

[Poetry]: https://img.shields.io/endpoint?url=https://python-poetry.org/badge/v0.json
[Poetry-url]: https://python-poetry.org/
[FastAPI]: https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi
[FastAPI-url]: https://fastapi.tiangolo.com/
[sqlalchemy]: https://img.shields.io/badge/SQLAlchemy-306998?logo=python&logoColor=white
[sqlalchemy-url]: https://www.sqlalchemy.org/
[Alembic]: https://img.shields.io/badge/Alembic-23374D?logo=alembic&logoColor=white
[Alembic-url]: https://alembic.sqlalchemy.org/
[Pydantic]: https://img.shields.io/badge/Pydantic-008489?logo=pydantic&logoColor=white
[Pydantic-url]: https://docs.pydantic.dev/latest/
[Passlib]: https://img.shields.io/badge/Passlib-3776AB?logo=python&logoColor=white
[Passlib-url]: https://passlib.readthedocs.io/en/stable/
[PyJWT]: https://img.shields.io/badge/PyJWT-FF9900?logo=python&logoColor=white
[PyJWT-url]: https://pyjwt.readthedocs.io/en/stable/
[FastAPIPagination]: https://img.shields.io/badge/FastAPI--Pagination-005571?logo=fastapi&logoColor=white
[FastAPIPagination-url]: https://github.com/uriyyo/fastapi-pagination
[aiosqlite]: https://img.shields.io/badge/aiosqlite-003B57?logo=sqlite&logoColor=white
[aiosqlite-url]: https://aiosqlite.omnilib.dev/en/latest/
[psycopg]: https://img.shields.io/badge/psycopg-2C5E8A?logo=postgresql&logoColor=white
[psycopg-url]: https://www.psycopg.org/psycopg3/docs/
[tzdata]: https://img.shields.io/badge/tzdata-0A192F?logo=clockify&logoColor=white
[tzdata-url]: https://pypi.org/project/tzdata/
[githubStar-url]: https://github.com/yourusername/machado-fintech-api/stargazers
[githubStar-img]: https://img.shields.io/github/stars/yourusername/machado-fintech-api?style=for-the-badge
[githubForks-url]: https://github.com/yourusername/machado-fintech-api/network
[githubForks-img]: https://img.shields.io/github/forks/yourusername/machado-fintech-api?style=for-the-badge
[githubIssues-url]: https://github.com/yourusername/machado-fintech-api/issues
[githubIssues-img]: https://img.shields.io/github/issues/yourusername/machado-fintech-api?style=for-the-badge
[githubLicense-url]: ./LICENSE
[githubLicense-img]: https://img.shields.io/github/license/yourusername/machado-fintech-api?style=for-the-badge
