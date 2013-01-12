#!/usr/bin/env python
#
# Copyright (C) 2012 Zeex
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import argparse
import cidl
import itertools
import os
import sys

EXPORT_PREFIX = 'sampgdk_'

idl_to_c_type_in = {
	'int'    : 'int',
	'bool'   : 'bool',
	'float'  : 'float',
	'char'   : 'char',
	'string' : 'const char *'
}

idl_to_c_type_out = {
	'int'    : 'int *',
	'bool'   : 'bool *',
	'float'  : 'float *',
	'char'   : 'char *',
	'string' : 'char **'
}

def get_param_c_type(p):
	try:
		if p.is_out():
			return idl_to_c_type_out[p.type]
		if p.is_in():
			return idl_to_c_type_in[p.type]
	except KeyError:
		if p.is_out():
			return '%s *' % p.type
		if p.is_in():
			return p.type
	return None

def value_to_c_literal(v):
	if v.is_bool():
		return ('false', 'true')[v.data]
	elif v.is_int():
		if v.is_hex():
			return '0x%s' % hex(v.data)[2:].upper()
		elif v.is_oct():
			return '%s' % oct(v.data)
		return '%s' % int(v.data)
	elif v.is_float():
		return '%s' % v.data
	elif v.is_char():
		return '\'%s\'' % v.data
	elif v.is_string():
		return '"%s"' % v.data
	return None

def params_to_string(params):
	return ', '.join(['%s %s' % (get_param_c_type(p), p.name) for p in params])

def params_to_string_no_types(params):
	return ', '.join(['%s' % p.name for p in params])

def is_out_param(p):
	return p.is_out()

def is_ref_param(p):
	return is_out_param(p) or p.type == 'string'

def is_value_param(p):
	return not is_ref_param(p)

def previous_and_next(iterable):
    prevs, items, nexts = itertools.tee(iterable, 3)
    prevs = itertools.chain([None], prevs)
    nexts = itertools.chain(itertools.islice(nexts, 1, None), [None])
    return itertools.izip(prevs, items, nexts)

def gen_constants(idl, header):
	if header is not None:
		for c in idl.constants:
			header.write('#define %s (%s)\n' % (c.name, value_to_c_literal(c.value)))
		header.write('\n')

def gen_natives(idl, header, source, api):
	natives = filter(lambda x: x.has_attr('native'), idl.functions)
	natives_with_source = filter(lambda x: x.get_attr('native').value != 'special', natives)

	if header is not None:
		header.write('#ifndef SAMPGDK_NATIVE_EXPORT\n')
		header.write('\t#define SAMPGDK_NATIVE_EXPORT SAMPGDK_EXPORT\n')
		header.write('#endif\n')

		header.write('#ifndef SAMPGDK_NATIVE_CALL\n')
		header.write('\t#define SAMPGDK_NATIVE_CALL SAMPGDK_CALL\n')
		header.write('#endif\n')

		header.write('#ifndef SAMPGDK_NATIVE\n')
		header.write('\t#define SAMPGDK_NATIVE(ret_type, func_and_params) \\\n')
		header.write('\t\tSAMPGDK_NATIVE_EXPORT ret_type SAMPGDK_NATIVE_CALL %s##func_and_params\n' % EXPORT_PREFIX)
		header.write('#endif\n')

		header.write('\n')

		for f in natives:
			header.write('SAMPGDK_NATIVE_EXPORT %s SAMPGDK_NATIVE_CALL %s%s(%s);\n' % (f.type, EXPORT_PREFIX, f.name, params_to_string(f.params)))
			header.write('#undef  %s\n' % f.name)
			header.write('#define %s %s%s\n\n' % (f.name, EXPORT_PREFIX, f.name))

		header.write('\n')

	if source is not None:
		for f in natives_with_source:
			source.write('SAMPGDK_NATIVE_EXPORT %s SAMPGDK_NATIVE_CALL %s%s(%s) {\n' % (f.type, EXPORT_PREFIX, f.name, params_to_string(f.params)))
			source.write('\tstatic AMX_NATIVE native;\n')
			source.write('\tstruct fakeamx *fa;\n')
			source.write('\t%s retval;\n' % f.type)

			if f.params:
				source.write('\tcell params[%d];\n' % (len(f.params) + 1))

				# Define local vaiables to store AMX heap addresses.
				for p in filter(is_ref_param, f.params):
					source.write('\tcell %s_;\n' % p.name)

			source.write('\tif (unlikely(native == NULL))\n')
			source.write('\t\tnative = native_lookup_warn_stub("%s");\n' % f.name)

			source.write('\tfakeamx_instance(&fa);\n')

			if f.params:
				# Call to fakeamx_push() for parameters.
				for pprev, p, pnext in previous_and_next(f.params):
					if is_ref_param(p):
						if p.type == 'char': # output string (const char *)
							source.write('\tfakeamx_push(fa, %s, &%s_);\n' % (pnext.name, p.name))
						elif p.type == 'string': # input string (char *)
							source.write('\tfakeamx_push_string(fa, %s, NULL, &%s_);\n' % (p.name, p.name))
						else:
							source.write('\tfakeamx_push(fa, 1, &%s_);\n' % p.name)

				# Fill the params array.
				source.write('\tparams[0] = %d * sizeof(cell);\n' % len(f.params))
				for index, p in enumerate(f.params, 1):
					if is_value_param(p):
						source.write('\tparams[%d] = %s;\n' % (index, 
							{
								'int'   : '(cell)%s' % p.name,
								'bool'  : '(cell)%s' % p.name,
								'char'  : '(cell)%s' % p.name,
								'float' : 'amx_ftoc(%s)' % p.name,
							}[p.type]
						))
					else:
						source.write('\tparams[%d] = %s_;\n' % (index, p.name))

			source.write('\tretval = (%s)native(&fa->amx, %s);\n' % (f.type, ('NULL', 'params')[bool(f.params)]))

			if f.params:
				# Copy data to output arguments.
				for pprev, p, pnext in previous_and_next(f.params):
					if is_ref_param(p):
						if p.type == 'string':
							pass
						elif p.type == 'char':
							source.write('\tfakeamx_get_string(fa, %s_, %s, %s);\n' % (p.name, p.name, pnext.name))
						else:
							source.write('\tfakeamx_get_%s(fa, %s_, %s);\n' % (
								{
									'int'   : "cell",
									'bool'  : "bool",
									'float' : "float"
								}[p.type]
							,	
							p.name, p.name))

				# Free previously allocated heap space (in reverse order).
				for p in reversed(filter(is_ref_param, f.params)):
					source.write('\tfakeamx_pop(fa, %s_);\n' % p.name)

			source.write('\treturn retval;\n')
			source.write('}\n\n')

		source.write('\n')

	if api is not None:
		for f in natives:
			api.write('%s%s\n' % (EXPORT_PREFIX, f.name))

def gen_callbacks(idl, header, source):
	callbacks = filter(lambda x: x.has_attr('callback'), idl.functions)

	if header is not None:
		header.write('#ifndef SAMPGDK_CALLBACK_EXPORT\n')
		header.write('\t#define SAMPGDK_CALLBACK_EXPORT PLUGIN_EXPORT\n')
		header.write('#endif\n')

		header.write('#ifndef SAMPGDK_CALLBACK_CALL\n')
		header.write('\t#define SAMPGDK_CALLBACK_CALL PLUGIN_CALL\n')
		header.write('#endif\n')

		header.write('#ifndef SAMPGDK_CALLBACK\n')
		header.write('\t#define SAMPGDK_CALLBACK(ret_type, func_and_params) \\\n')
		header.write('\t\tSAMPGDK_CALLBACK_EXPORT ret_type SAMPGDK_CALLBACK_CALL func_and_params\n')
		header.write('#endif\n')

		header.write('\n')

		for f in callbacks:
			header.write('SAMPGDK_CALLBACK_EXPORT %s SAMPGDK_CALLBACK_CALL %s(%s);\n' % (f.type, f.name, params_to_string(f.params)))

	if source is not None:
		for f in callbacks:
			source.write('typedef %s (PLUGIN_CALL *%s_type)(%s);\n' % (f.type, f.name, params_to_string(f.params)))
			source.write('bool %s_handler(AMX *amx, void *callback, cell *retval) {\n' % f.name)

			badret = f.get_attr('badret')
			if badret is not None:
				source.write('\tbool retval_;\n')

			# Declare local variables for temporary storage of callback arguments.
			for p in f.params:
				source.write('\t%s %s;\n' % (get_param_c_type(p), p.name))

			# Copy parameters from AMX stack.
			for index, p in enumerate(f.params):
				source.write('\t%s = amx_stack_get_arg_%s(amx, %d);\n' % (p.name,
					{
						'int'    : 'cell',
						'bool'   : 'bool',
						'float'  : 'float',
						'char'   : 'char',
						'string' : 'string'
					}[p.type], index)
				)

			# Invoke the callback function.
			if badret is not None:
				source.write('\tretval_ = ((%s_type)callback)(%s);\n' % (f.name, params_to_string_no_types(f.params)))
				source.write('\tif (retval != NULL)\n')
				source.write('\t\t*retval = (cell)retval_;\n')
			else:
				source.write('\t((%s_type)callback)(%s);\n' % (f.name, params_to_string_no_types(f.params)))

			# Free the memory allocated for strings.
			for p in filter(lambda p: p.type == 'string', f.params):
				source.write('\tfree((void*)%s);\n' % p.name)

			if badret is not None:
				source.write('\treturn (retval_ != %s);\n' % value_to_c_literal(badret.value))
			else:
				source.write('\treturn true;\n')

			source.write('}\n\n')

		source.write('int register_callbacks() {\n')
		source.write('\tint error;\n')

		for f in callbacks:
			source.write('\tif ((error = callback_add_handler("%s", %s_handler)) < 0)\n' % (f.name, f.name))
			source.write('\t\treturn error;\n')

		source.write('\t(void)error;\n')
		source.write('\treturn 0;\n')
		source.write('}\n\n')
		
def main(argv):
	argparser = argparse.ArgumentParser()

	argparser.add_argument('--idl', required=True)
	argparser.add_argument('--header')
	argparser.add_argument('--source')
	argparser.add_argument('--api')
	argparser.add_argument('--constants', dest='gen_constants', action='store_true')
	argparser.add_argument('--natives', dest='gen_natives', action='store_true')
	argparser.add_argument('--callbacks', dest='gen_callbacks', action='store_true')
	argparser.add_argument('--all', dest='gen_all', action='store_true')

	args = argparser.parse_args(argv[1:])

	try:
		idlparser = cidl.Parser()
		idl = idlparser.parse(open(args.idl, 'r').read())

		def ensure_path_ok(filename):
			directory = os.path.dirname(filename)
			if not os.path.exists(directory):
				os.mkdir(directory)

		header = None
		if args.header is not None:
			ensure_path_ok(args.header)
			header = open(args.header, 'w')
		source = None
		if args.source is not None:
			ensure_path_ok(args.source)
			source = open(args.source, 'w')
		api = None
		if args.api is not None:
			ensure_path_ok(args.api)
			api = open(args.api, 'w')

		if args.gen_constants or args.gen_all:
			gen_constants(idl, header)
		if args.gen_natives or args.gen_all:
			gen_natives(idl, header, source, api)
		if args.gen_callbacks or args.gen_all:
			gen_callbacks(idl, header, source)

	except cidl.Error as e:
		sys.stderr.write('%s\n' % e)

if __name__ == '__main__':
	main(sys.argv)