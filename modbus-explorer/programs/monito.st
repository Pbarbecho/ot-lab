(* monito.st - Taller 5, practica 1b
   OpenPLC como maestro Modbus TCP del simulador modbus-sim (172.28.0.30:5020).
   Slave device: Start Address 0 en todas las tablas.
     Discrete Inputs  size 2 -> %IX100.0 pulsador
     Coils            size 2 -> %QX100.0 led, %QX100.1 ventilador
     Input Registers  size 2 -> %IW100 temperatura x10, %IW101 CO2 ppm
     Holding - Read   size 2 -> %IW102 consigna x10, %IW103 umbral CO2
     Holding - Write  size 0
   Reglas de OpenPLC: solo ASCII (MatIEC) y, para que Monitoring muestre bien
   la tabla, una variable por linea con UN solo espacio (nombre, AT, %dir, :, TIPO;).
   Ojo: Monitoring toma como variable cualquier linea con la secuencia espacio-AT-espacio, comentarios incluidos. *)

PROGRAM monito
  VAR
    pulsador AT %IX100.0 : BOOL;
    led AT %QX100.0 : BOOL;
    ventilador AT %QX100.1 : BOOL;
    temp AT %IW100 : INT;
    co2 AT %IW101 : INT;
    consigna AT %IW102 : INT;
    umbral AT %IW103 : INT;
  END_VAR

  (* causa - efecto visible en el simulador *)
  led := pulsador;
  ventilador := co2 > umbral;
END_PROGRAM

CONFIGURATION Config0
  RESOURCE Res0 ON PLC
    TASK task0(INTERVAL := T#100ms, PRIORITY := 0);
    PROGRAM instance0 WITH task0 : monito;
  END_RESOURCE
END_CONFIGURATION
