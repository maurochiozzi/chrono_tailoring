===================================================================== test session starts =====================================================================
platform win32 -- Python 3.14.6, pytest-9.0.3, pluggy-1.6.0 -- \Python314\python.exe
cachedir: .pytest_cache
rootdir:\git\chrono_tailoring
configfile: pytest.ini
testpaths: tests
collected 46 items                                                                                                                                             

tests/integration/test_schedule_pipeline.py::TestInteractiveGanttExport::test_gantt_export_with_critical_arrows_only PASSED                              [  2%]
tests/integration/test_schedule_pipeline.py::TestInteractiveGanttExport::test_gantt_export_with_all_task_arrows PASSED                                   [  4%]
tests/unit/test_loader.py::TestLoadHolidays::test_loads_valid_dates PASSED                                                                               [  6%]
tests/unit/test_loader.py::TestLoadHolidays::test_skips_malformed_lines PASSED                                                                           [  8%]
tests/unit/test_loader.py::TestLoadHolidays::test_returns_empty_set_for_missing_file PASSED                                                              [ 10%] 
tests/unit/test_loader.py::TestLoadRawTasksFromCsv::test_loads_correct_number_of_tasks PASSED                                                            [ 13%]
tests/unit/test_loader.py::TestLoadRawTasksFromCsv::test_task_ids_match_csv PASSED                                                                       [ 15%] 
tests/unit/test_loader.py::TestLoadRawTasksFromCsv::test_task_names_parsed PASSED                                                                        [ 17%] 
tests/unit/test_loader.py::TestLoadRawTasksFromCsv::test_task_type_description_set PASSED                                                                [ 19%] 
tests/unit/test_loader.py::TestLoadRawTasksFromCsv::test_successors_ids_parsed PASSED                                                                    [ 21%] 
tests/unit/test_loader.py::TestLoadRawTasksFromCsv::test_predecessor_back_links_built PASSED                                                      [ 71%] 
tests/unit/test_time_calc.py::TestIsWorkingDay::test_saturday_not_working PASSED                                                                         [ 73%] 
tests/unit/test_time_calc.py::TestIsWorkingDay::test_sunday_not_working PASSED                                                                           [ 76%] 
tests/unit/test_time_calc.py::TestIsWorkingDay::test_holiday_not_working PASSED                                                                          [ 78%] 
tests/unit/test_time_calc.py::TestIsWorkingDay::test_non_holiday_monday_is_working PASSED                                                                [ 80%] 
tests/unit/test_time_calc.py::TestGetNextWorkingTime::test_zero_duration_returns_same_time PASSED                                                        [ 82%] 
tests/unit/test_time_calc.py::TestGetNextWorkingTime::test_short_duration_within_same_day PASSED                                                         [ 84%] 
tests/unit/test_time_calc.py::TestGetNextWorkingTime::test_duration_exactly_fills_day PASSED                                                             [ 86%] 
tests/unit/test_time_calc.py::TestGetNextWorkingTime::test_duration_spills_into_next_day PASSED                                                          [ 89%] 
tests/unit/test_time_calc.py::TestGetNextWorkingTime::test_skips_weekend PASSED                                                                          [ 91%] 
tests/unit/test_time_calc.py::TestGetNextWorkingTime::test_start_before_working_hours_advances_to_8am PASSED                                             [ 93%] 
tests/unit/test_time_calc.py::TestGetNextWorkingTime::test_start_after_working_hours_moves_to_next_day PASSED                                            [ 95%] 
tests/unit/test_time_calc.py::TestGetNextWorkingTime::test_skips_holiday PASSED                                                                          [ 97%] 
tests/unit/test_time_calc.py::TestGetNextWorkingTime::test_multi_day_duration PASSED                                                                     [100%] 

===================================================================== 46 passed in 2.47s ====================================================================== 