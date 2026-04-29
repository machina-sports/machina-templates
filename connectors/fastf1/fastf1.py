import fastf1

import pandas as pd


def get_session_data(request_data):
    try:
        # Enable FastF1 logging
        fastf1.set_log_level('DEBUG')
        
        params = request_data.get('params', {})
        print("\n\nsession_data params\n\n", params)
        
        year = params.get('session_year', 2019)
        event = params.get('session_name', 'Monza')
        session_type = params.get('session_type', 'Q')
        
        print(f"\n\nUsing year: {year}, event: {event}, session_type: {session_type}\n\n")
        
        session = fastf1.get_session(year, event, session_type)
        
        session.load()
        
        result = {
            "session": str(session),
            "event_name": getattr(session.event, 'name', 'Unknown Event'),
            "event_date": str(getattr(session.event, 'date', 'Unknown Date')),
            "session_type": getattr(session, 'session_type', 'Unknown Session Type'),
            "track_name": getattr(session.event, 'circuit_name', 'Unknown Track')
        }
        
        return {"status": True, "data": result, "message": "Session data retrieved successfully"}
        
    except Exception as e:
        print(f"Error getting session data: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return {
            "status": False,
            "data": f"Error: {str(e)}",
            "message": "Error getting session data"
        }


def get_driver_info(request_data):
    try:
        # Enable FastF1 logging
        fastf1.set_log_level('DEBUG')
        
        params = request_data.get('params', {})
        print("\n\ndriver_info params\n\n", params)
        
        year = params.get('year', 2023)
        driver = params.get('driver')
        
        print(f"\n\nUsing year: {year}, driver: {driver}\n\n")
        
        if not driver:
            # Get all drivers for the year
            drivers = fastf1.api.driver_info(year=year)
            drivers_list = []
            
            for _, row in drivers.iterrows():
                drivers_list.append({
                    "driver_number": row.get('DriverNumber', ''),
                    "driver_id": row.get('DriverId', ''),
                    "driver_code": row.get('Abbreviation', ''),
                    "first_name": row.get('FirstName', ''),
                    "last_name": row.get('LastName', ''),
                    "full_name": row.get('FullName', ''),
                    "team_name": row.get('TeamName', '')
                })
            
            return {"status": True, "data": drivers_list, "message": f"Driver information for {year} retrieved successfully"}
        else:
            # Get specific driver info
            driver_info = fastf1.api.driver_info(driver=driver, year=year)
            
            if driver_info.empty:
                return {"status": False, "data": None, "message": f"No information found for driver {driver} in {year}"}
            
            row = driver_info.iloc[0]
            driver_data = {
                "driver_number": row.get('DriverNumber', ''),
                "driver_id": row.get('DriverId', ''),
                "driver_code": row.get('Abbreviation', ''),
                "first_name": row.get('FirstName', ''),
                "last_name": row.get('LastName', ''),
                "full_name": row.get('FullName', ''),
                "team_name": row.get('TeamName', '')
            }
            
            return {"status": True, "data": driver_data, "message": f"Driver information for {driver} in {year} retrieved successfully"}
        
    except Exception as e:
        print(f"Error getting driver information: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return {
            "status": False,
            "data": f"Error: {str(e)}",
            "message": "Error getting driver information"
        }


def get_team_info(request_data):
    try:
        # Enable FastF1 logging
        fastf1.set_log_level('DEBUG')
        
        params = request_data.get('params', {})
        print("\n\nteam_info params\n\n", params)
        
        year = params.get('year', 2023)
        team = params.get('team')
        
        print(f"\n\nUsing year: {year}, team: {team}\n\n")
        
        if not team:
            # Get all teams for the year
            teams = fastf1.api.team_info(year=year)
            teams_list = []
            
            for _, row in teams.iterrows():
                teams_list.append({
                    "team_id": row.get('TeamId', ''),
                    "team_name": row.get('TeamName', ''),
                    "nationality": row.get('Nationality', '')
                })
            
            return {"status": True, "data": teams_list, "message": f"Team information for {year} retrieved successfully"}
        else:
            # Get specific team info
            team_info = fastf1.api.team_info(team=team, year=year)
            
            if team_info.empty:
                return {"status": False, "data": None, "message": f"No information found for team {team} in {year}"}
            
            row = team_info.iloc[0]
            team_data = {
                "team_id": row.get('TeamId', ''),
                "team_name": row.get('TeamName', ''),
                "nationality": row.get('Nationality', '')
            }
            
            return {"status": True, "data": team_data, "message": f"Team information for {team} in {year} retrieved successfully"}
        
    except Exception as e:
        print(f"Error getting team information: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return {
            "status": False,
            "data": f"Error: {str(e)}",
            "message": "Error getting team information"
        }


def get_race_schedule(request_data):
    try:
        # Enable FastF1 logging
        fastf1.set_log_level('DEBUG')
        
        params = request_data.get('params', {})
        print("\n\nrace_schedule params\n\n", params)
        
        year = params.get('year', 2023)
        
        print(f"\n\nUsing year: {year}\n\n")
        
        # Get race schedule for the year
        schedule = fastf1.get_event_schedule(year)
        events = []
        
        for _, row in schedule.iterrows():
            event_data = {
                "round_number": row.get('RoundNumber', ''),
                "country": row.get('Country', ''),
                "location": row.get('Location', ''),
                "event_name": row.get('EventName', ''),
                "circuit_name": row.get('CircuitName', ''),
                "event_date": str(row.get('EventDate', '')),
                "event_format": row.get('EventFormat', '')
            }
            events.append(event_data)
        
        return {"status": True, "data": events, "message": f"Race schedule for {year} retrieved successfully"}
        
    except Exception as e:
        print(f"Error getting race schedule: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return {
            "status": False,
            "data": f"Error: {str(e)}",
            "message": "Error getting race schedule"
        }


def get_lap_data(request_data):
    try:
        # Enable FastF1 logging
        fastf1.set_log_level('DEBUG')
        
        params = request_data.get('params', {})
        print("\n\nlap_data params\n\n", params)
        
        year = params.get('year', 2023)
        event = params.get('event', 'Monza')
        session_type = params.get('session_type', 'R')
        driver = params.get('driver')
        
        print(f"\n\nUsing year: {year}, event: {event}, session_type: {session_type}, driver: {driver}\n\n")
        
        # Get session
        session = fastf1.get_session(year, event, session_type)
        session.load()
        
        if driver:
            # Get laps for specific driver
            laps = session.laps.pick_driver(driver)
        else:
            # Get all laps
            laps = session.laps
        
        # Convert laps DataFrame to list of dictionaries
        laps_list = []
        for _, lap in laps.iterrows():
            lap_data = {
                "driver": lap.get('Driver', ''),
                "team": lap.get('Team', ''),
                "lap_number": lap.get('LapNumber', ''),
                "lap_time": str(lap.get('LapTime', '')),
                "sector_1_time": str(lap.get('Sector1Time', '')),
                "sector_2_time": str(lap.get('Sector2Time', '')),
                "sector_3_time": str(lap.get('Sector3Time', '')),
                "compound": lap.get('Compound', ''),
                "tyre_life": lap.get('TyreLife', ''),
                "is_personal_best": bool(lap.get('IsPersonalBest', False)),
                "position": lap.get('Position', '')
            }
            laps_list.append(lap_data)
        
        return {"status": True, "data": laps_list, "message": f"Lap data retrieved successfully"}
        
    except Exception as e:
        print(f"Error getting lap data: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return {
            "status": False,
            "data": f"Error: {str(e)}",
            "message": "Error getting lap data"
        }


def get_race_results(request_data):
    try:
        # Enable FastF1 logging
        fastf1.set_log_level('DEBUG')
        
        params = request_data.get('params', {})
        print("\n\nrace_results params\n\n", params)
        
        year = int(params.get('year', 2023))
        event = params.get('event', 'Monza')
        
        print(f"\n\nUsing year: {year}, event: {event}\n\n")
        
        # Get session
        session = fastf1.get_session(year, event, 'R')
        session.load()
        
        # Get race results
        results = session.results
        
        # Convert results DataFrame to list of dictionaries
        results_list = []
        for _, result in results.iterrows():
            result_data = {
                "position": result.get('Position', ''),
                "driver_number": result.get('DriverNumber', ''),
                "driver": result.get('Abbreviation', ''),
                "team": result.get('TeamName', ''),
                "grid_position": result.get('GridPosition', ''),
                "status": result.get('Status', ''),
                "points": result.get('Points', ''),
                "time": str(result.get('Time', '')),
                "fastest_lap": bool(result.get('FastestLap', False)),
                "fastest_lap_time": str(result.get('FastestLapTime', ''))
            }
            results_list.append(result_data)
        
        return {"status": True, "data": results_list, "message": f"Race results for {event} {year} retrieved successfully"}
        
    except Exception as e:
        print(f"Error getting race results: {str(e)}")
        print(f"Error type: {type(e)}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
        return {
            "status": False,
            "data": f"Error: {str(e)}",
            "message": "Error getting race results"
        }
