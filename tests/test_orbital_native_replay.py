"""Independent synthetic native-record writer; no physical orbital claims."""
import hashlib
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

import numpy as np

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from check_orbital_energy import verify_native_wfc_roundtrip


def synthetic_fixture(ik=2):
    integer=lambda value: int(value).to_bytes(4,'little',signed=True)
    real=lambda value: struct.pack('<d',float(value))
    digest=lambda value: hashlib.sha256(value).hexdigest()
    ng=3;k=[.125,-.0625,.1875];columns=[[.7,0.,0.],[.1,.8,0.],[.2,.3,.9]]
    millers=np.array([[1,0,-2],[-3,1,0],[0,0,0]],dtype='<i8')
    coefficients=np.empty((2,ng,24),dtype='<c16')
    for band in range(24):
        for g in range(ng):
            for spin in range(2):
                coefficients[spin,g,band]=complex(100*band+10*g+spin+.25, -10*band+g+.5*spin)
    coefficients[1,2,7]=complex(-0.,-0.)
    first=integer(ik)+b''.join(real(x) for x in k)+integer(1)+integer(0)+real(1.)
    second=b''.join(integer(x) for x in (17,ng,2,24))  # ngw need not equal selected count.
    third=b''.join(real(columns[column][axis]) for column in range(3) for axis in range(3))
    miller=b''.join(integer(millers[g,axis]) for g in range(ng) for axis in range(3))
    bands=[]
    for band in range(24):
        bands.append(b''.join(real(coefficients[spin,g,band].real)+real(coefficients[spin,g,band].imag)
                              for spin in range(2) for g in range(ng)))
    payloads=[first,second,third,miller]+bands
    raw=bytearray();records=[]
    for payload in payloads:
        records.append({'payload_offset':len(raw)+4,'payload_bytes':len(payload)})
        raw.extend(integer(len(payload)));raw.extend(payload);raw.extend(integer(len(payload)))
    h={'schema_version':1,'ik':ik,'k_cart_bohr_inv':k,'b_columns_bohr_inv':columns,
       'ispin':1,'gamma_only':False,'gamma_only_raw':0,'scalef':1.,'ngw':17,'igwx':ng,'npol':2,'nbnd':24,
       'file_bytes':len(raw),'format':{'endian':'little','record_marker_bytes':4,'integer_bytes':4,
       'logical_bytes':4,'real_bytes':8,'complex_bytes':16},'records':records,
       'record_payload_bytes':[len(p) for p in payloads],'header_payload_sha256':digest(first+second+third),
       'candidate_count':1,'miller_values_status':'PASS','coefficient_values_status':'PASS',
       'coefficient_bitwise_roundtrip_status':'PASS','source_sha256':digest(raw)}
    native={'schema_version':1,'qe_wfc_format_status':'PASS','metadata':h,'shape':[2,ng,24],
            'source_sha256':digest(raw),'miller_payload_sha256':digest(miller),
            'coefficient_payload_sha256':digest(b''.join(bands))}
    expected={'path':f'20260907T112107073262Z-G40-3f9731a6/scratch/mg_soc_qe_v1.save/wfc{ik}.dat',
              'bytes':len(raw),'sha256':digest(raw)}
    stored={'millers':millers,'coefficients':coefficients,'k_cart':np.array(k,dtype='<f8')}
    return native,stored,expected,bytes(raw)


class NativeReplayTests(unittest.TestCase):
    def setUp(self):
        self.native,self.stored,self.expected,self.raw=synthetic_fixture()

    def verify(self):
        return verify_native_wfc_roundtrip(self.native,self.stored,self.expected,2)

    def refresh_payload_claims(self):
        self.native['miller_payload_sha256']=hashlib.sha256(self.stored['millers'].astype('<i4').tobytes()).hexdigest()
        c=self.stored['coefficients']
        self.native['coefficient_payload_sha256']=hashlib.sha256(b''.join(c[:,:,b].tobytes() for b in range(24))).hexdigest()

    def test_complete_record_bytes_match_independent_writer_without_file_or_physics_calls(self):
        before={key:array.tobytes() for key,array in self.stored.items()}
        with patch.object(Path,'open',side_effect=AssertionError('Native export/read forbidden')), \
             patch.object(np.fft,'fftn',side_effect=AssertionError('No numerical reevaluation')):
            result=self.verify()
        self.assertEqual(result['status'],'PASS');self.assertEqual(result['sha256'],hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(result['bytes'],len(self.raw));self.assertEqual(result['records'],28)
        self.assertEqual({key:array.tobytes() for key,array in self.stored.items()},before)

    def test_changed_coefficient_cannot_hide_behind_refreshed_payload_hash(self):
        self.stored['coefficients'][0,1,23]+=1.
        self.refresh_payload_claims()
        with self.assertRaisesRegex(ValueError,'whole WFC hash'):self.verify()

    def test_relative_spin_phase_is_bound_by_whole_original_hash(self):
        self.stored['coefficients'][1]*=1j
        self.refresh_payload_claims()
        with self.assertRaisesRegex(ValueError,'whole WFC hash'):self.verify()

    def test_consistent_g_and_coefficient_permutation_is_still_not_native_order(self):
        self.stored['millers']=self.stored['millers'][[1,0,2]].copy()
        self.stored['coefficients']=self.stored['coefficients'][:,[1,0,2],:].copy()
        self.refresh_payload_claims()
        with self.assertRaisesRegex(ValueError,'whole WFC hash'):self.verify()

    def test_changed_miller_is_not_accepted_with_a_new_payload_claim(self):
        self.stored['millers'][0,0]+=1;self.refresh_payload_claims()
        with self.assertRaisesRegex(ValueError,'whole WFC hash'):self.verify()

    def test_original_empty_band_bytes_are_also_bound(self):
        self.stored['coefficients'][:,:,-1]=0.;self.refresh_payload_claims()
        with self.assertRaisesRegex(ValueError,'whole WFC hash'):self.verify()

    def test_header_change_not_hidden_by_refreshed_header_hash(self):
        h=self.native['metadata'];h['ngw']+=1
        headers=(struct.pack('<i3diid',2,*h['k_cart_bohr_inv'],1,0,1.)+
                 struct.pack('<4i',h['ngw'],3,2,24)+np.array(h['b_columns_bohr_inv'],dtype='<f8').tobytes())
        h['header_payload_sha256']=hashlib.sha256(headers).hexdigest()
        with self.assertRaisesRegex(ValueError,'whole WFC hash'):self.verify()

    def test_fake_g40_or_wrong_source_hash_fails(self):
        for location in ('native','metadata','expected'):
            with self.subTest(location=location):
                native,stored,expected,_=synthetic_fixture()
                if location=='native':native['source_sha256']='b'*64
                if location=='metadata':native['metadata']['source_sha256']='b'*64
                if location=='expected':expected['sha256']='b'*64
                with self.assertRaisesRegex(ValueError,'source hash'):
                    verify_native_wfc_roundtrip(native,stored,expected,2)
        self.expected['path']=self.expected['path'].replace('G40','D40')
        with self.assertRaisesRegex(ValueError,'original G40 slot'):self.verify()

    def test_agreeing_self_declared_hashes_do_not_replace_the_actual_file_bytes(self):
        self.native['source_sha256']=self.native['metadata']['source_sha256']=self.expected['sha256']='b'*64
        with self.assertRaisesRegex(ValueError,'whole WFC hash'):self.verify()

    def test_slot_and_header_coordinate_mismatch_rejected(self):
        with self.assertRaisesRegex(ValueError,'original G40 slot'):
            verify_native_wfc_roundtrip(self.native,self.stored,self.expected,1)
        self.native['metadata']['k_cart_bohr_inv'][0]+=1.
        with self.assertRaisesRegex(ValueError,'Cartesian k'):self.verify()

    def test_record_envelope_and_file_size_claims_are_checked(self):
        for change in ('offset','length','count','bytes'):
            native,stored,expected,_=synthetic_fixture()
            if change=='offset':native['metadata']['records'][-1]['payload_offset']+=1
            if change=='length':native['metadata']['record_payload_bytes'][-1]-=16
            if change=='count':native['metadata']['records'].pop()
            if change=='bytes':expected['bytes']+=1
            with self.subTest(change=change):
                with self.assertRaises(ValueError):verify_native_wfc_roundtrip(native,stored,expected,2)

    def test_only_observed_byte_format_and_unique_candidate_are_supported(self):
        for field,value in [('endian','big'),('record_marker_bytes',8),('integer_bytes',8),('logical_bytes',8)]:
            native,stored,expected,_=synthetic_fixture();native['metadata']['format'][field]=value
            with self.subTest(field=field):
                with self.assertRaisesRegex(ValueError,'byte format'):verify_native_wfc_roundtrip(native,stored,expected,2)
        self.native['metadata']['candidate_count']=2
        with self.assertRaisesRegex(ValueError,'not unique'):self.verify()

    def test_dtype_nonfinite_integer_narrowing_and_shape_rejected(self):
        for change in ('float_miller','overflow','nan','one_spin','fewer_bands'):
            native,stored,expected,_=synthetic_fixture()
            if change=='float_miller':stored['millers']=stored['millers'].astype('<f8')
            if change=='overflow':stored['millers'][0,0]=2**32+1
            if change=='nan':stored['coefficients'][0,0,0]=complex(0,np.nan)
            if change=='one_spin':stored['coefficients']=stored['coefficients'][:1]
            if change=='fewer_bands':stored['coefficients']=stored['coefficients'][:,:,:23]
            with self.subTest(change=change):
                with self.assertRaises(ValueError):verify_native_wfc_roundtrip(native,stored,expected,2)


if __name__=='__main__':unittest.main()
