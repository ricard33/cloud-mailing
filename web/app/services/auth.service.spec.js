/* eslint-env jasmine */
/* global inject, module */

// (function () {
'use strict';

/* jasmine specs for directives go here */

describe('auth services:', function () {
    // var $window;

    // // You can copy/past this beforeEach
    // beforeEach(module(function ($provide) {
    //
    // }));

    // beforeEach(function () {
    //     this.addMatchers({
    //         toEqualData: function (expected) {
    //             return angular.equals(this.actual, expected);
    //         }
    //     });
    // });

    var $httpBackend;
    var auth;

    beforeEach(module('cm.auth'));

    beforeEach(inject(function ($injector) {
        $httpBackend = $injector.get('$httpBackend');
        auth = $injector.get('auth');
    }));

    afterEach(function () {
        $httpBackend.verifyNoOutstandingExpectation();
        $httpBackend.verifyNoOutstandingRequest();
    });

    // describe('getting user', function () {

    it('should should cache the request', function () {
        $httpBackend.expect('GET', '/api/authenticate').respond({username: 'admin', is_superuser: true});

        var ret = auth.getCurrentUser();
        $httpBackend.flush();
        auth.getCurrentUser();
        expect(ret.username).toEqual('admin');

    });

    // it('can get mailing details', inject(function (api) {
    //     var data = {id: 1, domain: 'example.org', status: 'RUNNING'};
    //     $httpBackend.expectGET('/api/mailings/1').respond(data);
    //
    //     var ret = api.mailings.get({id: 1});
    //     $httpBackend.flush();
    //     expect(ret).toEqualData(data);
    //
    // }));
    //
    // it('can set mailing in pause', inject(function (api) {
    //     var data = {id: 1, domain: 'example.org', status: 'RUNNING'};
    //     $httpBackend.expectPATCH('/api/mailings/1', data = {status: 'PAUSED'}).respond(data);
    //
    //     var ret = api.mailings.patch({id: 1}, {status: 'PAUSED'});
    //     $httpBackend.flush();
    //     expect(ret['status']).toEqualData('PAUSED');
    //
    // }));
    // });
});

// }());
