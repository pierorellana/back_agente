# Backend Agente IA

Backend en Python con FastAPI y una estructura inspirada en arquitectura hexagonal.

## Estructura

```text
app/
├── api/                 # Adaptador de entrada HTTP: routers, deps y handlers
├── application/         # Casos de uso, servicios de aplicacion, puertos y DTOs
├── domain/              # Entidades, reglas de negocio y errores del dominio
├── infrastructure/      # Adaptadores externos: config y clientes Notion
└── main.py              # Punto de entrada FastAPI
```

## Principios

- `api` no contiene reglas de negocio.
- `application` coordina casos de uso y depende de puertos, no de detalles externos.
- `domain` no depende de FastAPI ni librerias de infraestructura.
- `infrastructure` implementa los puertos definidos por la aplicacion.

## Instalacion

```bash
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements/base.txt
```

## Variables de entorno

Copia `.env.example` a `.env` y ajusta los valores necesarios.

```env
APP_NAME=backend-agente-ia
APP_DEBUG=false
NOTION_TOKEN=ntn_xxxxxxxxx
NOTION_ROOT_PAGE_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
NOTION_DATABASE_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
NOTION_VERSION=2026-03-11
NOTION_TABLES_MAP_PATH=config/notion_tables.json
```

## Ejecucion

```bash
uvicorn app.main:app --reload
```

- API: http://localhost:8000
- Swagger: http://localhost:8000/docs
- Notion connection check: http://localhost:8000/api/notion/connection
- Notion tables discovery: http://localhost:8000/api/notion/tables/discover
- Insurance providers: http://localhost:8000/api/insurance-providers
- Insurance plans: http://localhost:8000/api/insurance-plans
- Users: http://localhost:8000/api/users
- Specialties: http://localhost:8000/api/specialties
- Hospitals: http://localhost:8000/api/hospitals
- Symptoms: http://localhost:8000/api/symptoms
- Hospital specialties: http://localhost:8000/api/hospital-specialties

Los endpoints de catalogos usan `GeneralResponse`, y `data` contiene directamente el arreglo:

```json
{
  "success": true,
  "message": "Insurance providers loaded",
  "data": [
    {
      "provider_id": "prov_bluecare",
      "provider_name": "BlueCare Health"
    }
  ],
  "error": null
}
```

## Mapa de tablas de Notion

Si la pagina de Notion contiene varias tablas, sincroniza el mapa con:

```bash
curl -X POST http://localhost:8000/api/notion/tables/sync
```

Esto crea `config/notion_tables.json` con el `database_id`, `data_source_id` y propiedades de cada tabla encontrada.

## Tests

```bash
pytest
```

## Siguiente paso

Cuando definas el flujo del backend, agrega cada modulo siguiendo este recorrido:

```text
api/router -> application/use_case -> application/port -> infrastructure/adapter
                         |
                         v
                      domain
```
