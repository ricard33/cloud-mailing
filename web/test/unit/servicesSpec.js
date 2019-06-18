'use strict';

/* jasmine specs for directives go here */

describe('services:', function () {
    var $window;

    // You can copy/past this beforeEach
    beforeEach(module(function ($provide) {

    }));

    beforeEach(function(){
        jasmine.addMatchers({
            toEqualData: function(util, customEqualityTesters) {
                return {
                    compare: function(actual, expected) {
                        return {
                            pass: angular.equals(actual, expected)
                        };
                    }
                };
            }
        });
    });

    beforeEach(module('cm.services'));

    describe('API:', function () {
        var $httpBackend;

        beforeEach(inject(function (_$httpBackend_) {
            $httpBackend = _$httpBackend_;
        }));


        it('should use specific url for os/cpu API', inject(function (api) {
            var data = {total: 0, user: 0, nice: 0, system:0, idle: 0, total_per_cpu: 0};
            $httpBackend.expectGET('/api/os/cpu').respond(data)

            var ret = api.cpu.get();
            $httpBackend.flush();
            expect(ret).toEqualData(data);

        }));

        it('can get mailing details', inject(function (api) {
            var data = {id: 1, domain: 'example.org', status: 'RUNNING'};
            $httpBackend.expectGET('/api/mailings/1').respond(data)

            var ret = api.mailings.get({id: 1});
            $httpBackend.flush();
            expect(ret).toEqualData(data);

        }));

        it('can set mailing in pause', inject(function (api) {
            var data = {id: 1, domain: 'example.org', status: 'RUNNING'};
            $httpBackend.expectPATCH('/api/mailings/1', data={status: 'PAUSED'}).respond(data)

            var ret = api.mailings.patch({id: 1}, {status: 'PAUSED'});
            $httpBackend.flush();
            expect(ret['status']).toEqualData('PAUSED');

        }));
    });
});
