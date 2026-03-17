# src/validation/schema_registry.py

SCHEMA_MATRICULA = {
    "nombre": "Matrícula",
    "required": [
        "rut",
        "nombre",
        "codigo_curso",
    ],
    "optional": [
        "estado_matricula",
        "fecha_retiro",
        "motivo_retiro",
        "apellido_paterno",
        "apellido_materno",
        "nombres_alumno",
        "nacimiento",
        "edad",
        "sexo",
        "nacionalidad",
        "comuna",
        "repitente",
        "hora_matricula",
        "numero_matricula",
    ],
    "aliases": {
        "rut": [
            "rut",
            "numero rut",
            "número rut",
            "rut alumno",
            "rut estudiante",
            "run",
        ],
        "nombre": [
            "nombre",
        ],
        "codigo_curso": [
            "codigo curso",
            "código curso",
            "ccurso",
            "curso",
            "curnombrecorto",
        ],
        "estado_matricula": [
            "estado matricula",
            "estado matrícula",
        ],
        "fecha_retiro": [
            "fecha retiro",
            "fecha_retiro",
            "retiro",
        ],
        "motivo_retiro": [
            "motivo retiro",
            "motivo_retiro",
        ],
        "apellido_paterno": [
            "apellido paterno",
        ],
        "apellido_materno": [
            "apellido materno",
        ],
        "nombres_alumno": [
            "nombres alumno",
        ],
        "nacimiento": [
            "nacimiento",
            "fecha nacimiento",
        ],
        "edad": [
            "edad",
        ],
        "sexo": [
            "sexo",
        ],
        "nacionalidad": [
            "nacionalidad",
        ],
        "comuna": [
            "comuna",
        ],
        "repitente": [
            "repitente",
        ],
        "hora_matricula": [
            "hora matricula",
            "hora matrícula",
        ],
        "numero_matricula": [
            "numero matricula",
            "número matrícula",
            "número matricula",
        ],
    },
}

SCHEMA_ASISTENCIA = {
    "nombre": "Asistencia",
    "required": [
        "nombre",
        "rut",
        "curso",
        "porcen",
    ],
    "optional": [
        "fecha",
        "cur_nombre",
        "cur_nombre_corto",
        "codigo_curso",
        "id_alumno",
        "presente",
        "ausente",
        "dias",
    ],
    "aliases": {
        "fecha": [
            "fecha",
        ],
        "cur_nombre": [
            "curnombre",
        ],
        "cur_nombre_corto": [
            "curnombrecorto",
        ],
        "codigo_curso": [
            "ccurso",
            "codigo curso",
            "código curso",
        ],
        "curso": [
            "curso",
        ],
        "nombre": [
            "nombre",
            "nombre alumno",
        ],
        "rut": [
            "rut",
            "numero rut",
            "número rut",
        ],
        "id_alumno": [
            "idalumno",
            "id alumno",
        ],
        "presente": [
            "presente",
        ],
        "ausente": [
            "ausente",
        ],
        "porcen": [
            "porcen",
            "porcentaje",
        ],
        "dias": [
            "dias",
            "días",
        ],
    },
}

SCHEMA_DESISTE = {
    "nombre": "Desiste",
    "required": [
        "estado_matricula",
        "rut",
        "nombre",
        "codigo_curso",
    ],
    "optional": [
        "numero_matricula",
        "fecha_retiro",
        "motivo_retiro",
        "apellido_paterno",
        "apellido_materno",
        "nombres_alumno",
        "nacimiento",
        "edad",
        "sexo",
        "nacionalidad",
        "comuna",
    ],
    "aliases": {
        "estado_matricula": [
            "estado matricula",
            "estado matrícula",
        ],
        "numero_matricula": [
            "numero matricula",
            "número matrícula",
            "número matricula",
        ],
        "fecha_retiro": [
            "fecha retiro",
        ],
        "motivo_retiro": [
            "motivo retiro",
        ],
        "codigo_curso": [
            "codigo curso",
            "código curso",
            "ccurso",
            "curso",
        ],
        "rut": [
            "numero rut",
            "número rut",
            "rut",
        ],
        "apellido_paterno": [
            "apellido paterno",
        ],
        "apellido_materno": [
            "apellido materno",
        ],
        "nombres_alumno": [
            "nombres alumno",
        ],
        "nombre": [
            "nombre",
        ],
        "nacimiento": [
            "nacimiento",
        ],
        "edad": [
            "edad",
        ],
        "sexo": [
            "sexo",
        ],
        "nacionalidad": [
            "nacionalidad",
        ],
        "comuna": [
            "comuna",
        ],
    },
}

SCHEMA_ATRASOS = {
    "nombre": "Atrasos",
    "required": [
        "fecha_atraso",
        "rut",
        "nombre",
        "codigo_curso",
    ],
    "optional": [
        "id_atraso",
        "tipo_atraso",
        "alumno_id",
        "justifica",
        "justifica_fecha",
        "periodo",
        "hora",
    ],
    "aliases": {
        "id_atraso": [
            "idatraso",
            "id atraso",
        ],
        "fecha_atraso": [
            "atrafecha",
            "fecha atraso",
            "fecha",
        ],
        "codigo_curso": [
            "curnombrecorto",
            "codigo curso",
            "ccurso",
            "curso",
        ],
        "rut": [
            "alurut",
            "rut",
            "numero rut",
            "número rut",
        ],
        "nombre": [
            "alunombre",
            "nombre",
            "nombre alumno",
        ],
        "tipo_atraso": [
            "tiponombre",
            "tipo",
            "tipo atraso",
        ],
        "alumno_id": [
            "alumno",
            "idalumno",
            "id alumno",
        ],
        "justifica": [
            "justifica",
            "justificado",
        ],
        "justifica_fecha": [
            "justificafecha",
            "fecha justifica",
            "fecha justificacion",
        ],
        "periodo": [
            "per0",
            "per1",
            "periodo",
            "periodo clase",
        ],
        "hora": [
            "hora",
        ],
    },
}

SCHEMAS_DISPONIBLES = {
    "matricula": SCHEMA_MATRICULA,
    "asistencia": SCHEMA_ASISTENCIA,
    "desiste": SCHEMA_DESISTE,
    "atrasos": SCHEMA_ATRASOS,
}