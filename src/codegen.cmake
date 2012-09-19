# Work around unability to set environment variables for custom commands.

foreach(path IN LISTS PYTHONPATH)
	if(WIN32)
		set(ENV{PYTHONPATH} "${path};$ENV{PYTHONPATH}")
	else()
		set(ENV{PYTHONPATH} "${path}:$ENV{PYTHONPATH}")
	endif()
endforeach()

if(NOT PYTHON)
	find_package(PythonInterp 2.7 REQUIRED)
	set(PYTHON ${PYTHON_EXECUTABLE})
endif()

if(NOT PATH)
	set(PATH "${CMAKE_CURRENT_SOURCE_DIR}/codegen.py")
endif()

if(IDL_FILE)
	list(APPEND ARGS "--idl=${IDL_FILE}")
endif()
if(HEADER_FILE)
	list(APPEND ARGS "--header=${HEADER_FILE}")
endif()
if(SOURCE_FILE)
	list(APPEND ARGS "--source=${SOURCE_FILE}")
endif()
if(EXPORTS_FILE)
	list(APPEND ARGS "--exports=${EXPORTS_FILE}")
endif()

execute_process(COMMAND ${PYTHON} ${PATH} "--all" ${ARGS}
	ERROR_VARIABLE PYTHON_ERRORS OUTPUT_VARIABLE PYTHON_OUTPUT)

if(OUTPUT_VARIABLE)
	message(${PYTHON_OUTPUT})
endif()
if(PYTHON_ERRORS)
	message(FATAL_ERROR ${PYTHON_ERRORS})
endif()
