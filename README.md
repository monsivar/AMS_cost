
# AMS Costs (hour/day/month) – Home Assistant custom component

Denne integrasjonen beregner kostnader basert på:
- **Pris (kr/kWh)** – f.eks. sensor.strompris_effektiv_denne_time_2
- **Houruse (kWh denne timen)** – f.eks. sensor.ams_f2c6_houruse
- **TPI (akkumulert kWh)** – f.eks. sensor.ams_f2c6_tpi (for nøyaktig dag/mnd akkumulasjon)
- **Threshold (effektledd-trinn)** – f.eks. sensor.ams_f2c6_threshold (5/10/15/20)

## Installasjon
1. Pakk ut mappen `custom_components/ams_costs/` i din Home Assistant-konfigmappe.
2. Restart Home Assistant (full omstart).
3. Gå til **Settings → Devices & Services → Add Integration** og velg **AMS Costs**.
4. Velg kildesensorer og (valgfritt) tilpass effektledd-satser.

## Sensorer
- `sensor.ams_cost_hour` – Kostnad denne timen = houruse * price
- `sensor.ams_cost_today` – Kostnad i dag = (sum delta_kWh * price) + (effektledd / dager_i_mnd)
- `sensor.ams_cost_month` – Kostnad denne måneden = (sum delta_kWh * price) + (effektledd)

## Notater
- Lagrer akkumulert state i HA Storage og tåler omstarter.
- Spike-guard: ignorerer TPI-delta > 10 kWh mellom to events (kan justeres i koden).
