(* secuencia_sfc.st - Taller 5, practica 1b - version SFC (Grafcet textual IEC 61131-3)
   Mismo mapa que monito.st: el PLC sondea modbus-sim (172.28.0.30:5020, Start 0).
   Etapas: Reposo -> (pulsador) -> Marcha [led] -> (co2 > umbral) -> Ventilando [led, ventilador]
           -> (co2 <= umbral) -> Marcha ; (NOT pulsador) -> Reposo.
   Reglas de OpenPLC: solo ASCII; una variable por linea con UN solo espacio (nombre, AT, %dir, :, TIPO;).
   Monitoring toma como variable toda linea con la secuencia espacio-AT-espacio, comentarios incluidos. *)

PROGRAM secuencia
  VAR
    pulsador AT %IX100.0 : BOOL;
    led AT %QX100.0 : BOOL;
    ventilador AT %QX100.1 : BOOL;
    temp AT %IW100 : INT;
    co2 AT %IW101 : INT;
    consigna AT %IW102 : INT;
    umbral AT %IW103 : INT;
  END_VAR

  INITIAL_STEP Reposo:
  END_STEP

  TRANSITION FROM Reposo TO Marcha
    := pulsador;
  END_TRANSITION

  STEP Marcha:
    led(N);
  END_STEP

  TRANSITION FROM Marcha TO Ventilando
    := co2 > umbral;
  END_TRANSITION

  TRANSITION FROM Marcha TO Reposo
    := NOT pulsador;
  END_TRANSITION

  STEP Ventilando:
    led(N);
    ventilador(N);
  END_STEP

  TRANSITION FROM Ventilando TO Marcha
    := co2 <= umbral;
  END_TRANSITION

  TRANSITION FROM Ventilando TO Reposo
    := NOT pulsador;
  END_TRANSITION
END_PROGRAM

CONFIGURATION Config0
  RESOURCE Res0 ON PLC
    TASK task0(INTERVAL := T#100ms, PRIORITY := 0);
    PROGRAM instance0 WITH task0 : secuencia;
  END_RESOURCE
END_CONFIGURATION
