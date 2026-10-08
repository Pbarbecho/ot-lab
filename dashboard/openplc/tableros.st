(* tableros.st - Taller 2, reto lamina 36
   OpenPLC (maestro) sondea los tableros de las laminas 30 y 31 en modbus-sim
   (172.28.0.30:5020) y aplica una logica de control con umbrales.
   Cargar antes el tablero "Reto captura completa (lamina 32)" en server.json.

   Slave Devices -> Add new device: Generic Modbus TCP Device, Slave ID 1,
   IP 172.28.0.30, puerto 5020:
     Discrete Inputs           start 0 size 4 -> %IX100.0 .. %IX100.3 (FC 02)
     Coils                     start 0 size 5 -> %QX100.0 .. %QX100.4 (FC 15)
     Input Registers           start 0 size 4 -> %IW100 .. %IW103     (FC 04)
     Holding Registers - Read  start 0 size 5 -> %IW104 .. %IW108     (FC 03)
     Holding Registers - Write start 5 size 3 -> %QW100 .. %QW102     (FC 16)
   El PLC escribe en HR 5-7 y NO en HR 0-4: las consignas las cambia el
   operador (dashboard, FC 06) y el PLC solo las lee.

   Logica (temperatura y consignas x10):
     alarma_temp = temperatura > consigna T          -> LED rojo
     ventilador  = CO2 > umbral CO2  o  alarma_temp
     marcha_ok   = marcha y no paro y no emergencia
     LED verde   = marcha_ok y no alarma_temp
     bomba       = marcha_ok y puerta cerrada
     sirena      = emergencia
   Salidas a HR 5-7: estado (bits de las 5 salidas), exceso de temperatura
   (x10, 0 si no hay alarma) y un contador de ciclos.

   Reglas de OpenPLC: solo ASCII (MatIEC) y, para que Monitoring muestre bien
   la tabla, una variable por linea con UN solo espacio: nombre AT %dir : TIPO; *)

PROGRAM tableros
  VAR
    marcha AT %IX100.0 : BOOL;
    paro AT %IX100.1 : BOOL;
    emergencia AT %IX100.2 : BOOL;
    puerta AT %IX100.3 : BOOL;
    led_verde AT %QX100.0 : BOOL;
    led_rojo AT %QX100.1 : BOOL;
    ventilador AT %QX100.2 : BOOL;
    bomba AT %QX100.3 : BOOL;
    sirena AT %QX100.4 : BOOL;
    temp AT %IW100 : INT;
    humedad AT %IW101 : INT;
    co2 AT %IW102 : INT;
    presion AT %IW103 : INT;
    consigna_t AT %IW104 : INT;
    consigna_hr AT %IW105 : INT;
    umbral_co2 AT %IW106 : INT;
    vel_ventilador AT %IW107 : INT;
    modo AT %IW108 : INT;
    estado AT %QW100 : INT;
    exceso_temp AT %QW101 : INT;
    ciclos AT %QW102 : INT;
  END_VAR
  VAR
    alarma_temp : BOOL;
    marcha_ok : BOOL;
  END_VAR

  alarma_temp := temp > consigna_t;
  marcha_ok := marcha AND NOT paro AND NOT emergencia;

  led_rojo := alarma_temp OR emergencia;
  ventilador := (co2 > umbral_co2) OR alarma_temp;
  led_verde := marcha_ok AND NOT alarma_temp;
  bomba := marcha_ok AND NOT puerta;
  sirena := emergencia;

  estado := 0;
  IF led_verde THEN estado := estado + 1; END_IF;
  IF led_rojo THEN estado := estado + 2; END_IF;
  IF ventilador THEN estado := estado + 4; END_IF;
  IF bomba THEN estado := estado + 8; END_IF;
  IF sirena THEN estado := estado + 16; END_IF;

  IF alarma_temp THEN
    exceso_temp := temp - consigna_t;
  ELSE
    exceso_temp := 0;
  END_IF;

  ciclos := ciclos + 1;
  IF ciclos > 30000 THEN
    ciclos := 0;
  END_IF;
END_PROGRAM

CONFIGURATION Config0
  RESOURCE Res0 ON PLC
    TASK task0(INTERVAL := T#100ms, PRIORITY := 0);
    PROGRAM instance0 WITH task0 : tableros;
  END_RESOURCE
END_CONFIGURATION
