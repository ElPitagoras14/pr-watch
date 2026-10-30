## MODIFIED Requirements

### Requirement: Claves configurables

La configuración SHALL exponer al menos: el proveedor de forja, los ajustes propios del proveedor activo, el intervalo de sondeo, el tope de pull requests por bloque, los minutos que un pull request fusionado o cerrado permanece visible, y si las notificaciones están activadas.

Los ajustes propios de cada proveedor SHALL vivir en una tabla con el nombre del proveedor, para que añadir otro proveedor no obligue a renombrar ni mezclar claves:

- `[github]`: la organización de GitHub o en su lugar la cuenta personal (`org` o `user`; si vienen las dos, gana la organización y se avisa).
- `[gitlab]`: la dirección de la instancia (`host`, por defecto `https://gitlab.com`) y el grupo vigilado o en su lugar el espacio de nombres personal (`group` o `user`; si vienen los dos, gana el grupo y se avisa).

El tope SHALL llamarse `max_per_block` y SHALL aplicarse a CADA bloque por separado, no a la suma de los dos.

#### Scenario: Valores por defecto
- **WHEN** la aplicación arranca con la configuración recién creada
- **THEN** usa `github` como proveedor, ninguna organización, 60 segundos de intervalo, 5 pull requests por bloque, 15 minutos de caducidad y las notificaciones apagadas

#### Scenario: Intervalo fuera de rango
- **WHEN** la configuración declara un intervalo de sondeo menor a 30 segundos
- **THEN** la aplicación lo eleva a 30 segundos y avisa, para no consumir el límite de peticiones de la forja

#### Scenario: Tope fuera de rango
- **WHEN** la configuración declara un tope por bloque menor que 1 o mayor que 20
- **THEN** la aplicación lo ajusta al extremo más cercano y avisa, porque un tope de cero dejaría la lista vacía y uno demasiado alto desbordaría un panel sin desplazamiento

#### Scenario: Proveedor desconocido
- **WHEN** la configuración declara un proveedor que la aplicación no implementa
- **THEN** la aplicación arranca sin sondear, el tooltip y el panel indican que el proveedor no está soportado, y el archivo no se modifica

#### Scenario: Tabla del proveedor inactivo
- **WHEN** la configuración declara `[github]` y `[gitlab]` a la vez
- **THEN** ambas se conservan en el archivo y solo se aplica la del proveedor activo, para que alternar entre proveedores no obligue a volver a escribir el ámbito

#### Scenario: Instancia de GitLab por defecto
- **WHEN** el proveedor es `gitlab` y `[gitlab] host` no está declarado o está vacío
- **THEN** la aplicación usa `https://gitlab.com` y avisa de que asumió la nube pública

#### Scenario: Host con barra final o sin esquema
- **WHEN** el host declarado termina en `/` o no lleva esquema, como `gitlab.empresa.com`
- **THEN** la aplicación lo normaliza —quita la barra final y asume `https://`— y usa el valor normalizado

#### Scenario: Host inválido
- **WHEN** el host declarado no es una dirección utilizable, por ejemplo porque no es texto o usa un esquema que no es `http` ni `https`
- **THEN** la aplicación avisa, no sondea y deja el archivo intacto, en lugar de intentar peticiones contra una dirección sin sentido

## ADDED Requirements

### Requirement: Cambiar de proveedor conserva lo que no depende del proveedor

Cambiar el proveedor o la instancia MUST NOT alterar los ajustes que no dependen de ellos —intervalo de sondeo, tope por bloque, caducidad y notificaciones—, ni borrar del archivo la configuración del proveedor que se deja de usar.

#### Scenario: Ida y vuelta entre proveedores
- **WHEN** el usuario pasa de GitHub a GitLab y después vuelve a GitHub
- **THEN** la organización de GitHub que tenía configurada sigue ahí y no hay que volver a elegirla

#### Scenario: Los ajustes de sondeo sobreviven
- **WHEN** el usuario cambia de proveedor
- **THEN** su intervalo, su tope por bloque y su preferencia de notificaciones siguen siendo los mismos
