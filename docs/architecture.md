# Arquitectura

Este backend queda preparado para trabajar con arquitectura hexagonal.

## Capas

`api`

Adaptador de entrada. Recibe HTTP con FastAPI, valida DTOs de request y llama a servicios o casos de uso de la capa de aplicacion.

`application`

Orquesta casos de uso. Aqui viven los DTOs, servicios de aplicacion y puertos que describen lo que necesita el negocio.

`domain`

Contiene reglas de negocio puras y errores. No importa FastAPI ni clientes externos.

`infrastructure`

Implementa adaptadores de salida. En este proyecto, el adaptador principal es Notion.

## Flujo recomendado

```text
HTTP -> api/router -> application/service -> domain
                                      |
                                      v
                            application/ports
                                      |
                                      v
                          infrastructure/adapters
```

## Como agregar un modulo

1. Define entidades y reglas en `app/domain`.
2. Crea DTOs en `app/application/dtos`.
3. Define puertos en `app/application/ports` cuando necesites datos de Notion u otro servicio externo.
4. Implementa esos puertos en `app/infrastructure`.
5. Expone el caso de uso desde un router en `app/api/routers`.
6. Registra dependencias en `app/api/deps.py`.
