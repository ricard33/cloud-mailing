'use strict';

/* jasmine specs for controllers go here */
describe('CM controllers', function () {
    var $window;

    // You can copy/past this beforeEach
    beforeEach(module(function ($provide) {

        $window = {
            // now, $window.location.path will update that empty object
            location: {},
            history: {
                back: function () {
                }
            },
            // we keep the reference to window.document
            document: window.document
        };

        // We register our new $window instead of the old
        $provide.constant('$window', $window);
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

    beforeEach(module('app'));

    describe('DashboardController', function () {
        var scope, ctrl, $httpBackend;

        beforeEach(inject(function (_$httpBackend_, $rootScope, $controller) {
            $httpBackend = _$httpBackend_;

            //$httpBackend.expectGET('/api/customers/').
            //    respond({
            //        results: [
            //            {name: 'My customer'},
            //            {name: 'Other customer'}
            //        ]
            //    });
            //
            //scope = $rootScope.$new();
            //ctrl = $controller('CustomersListCtrl', {$scope: scope});
        }));


        it('should do something', function () {
            //expect(scope.customers).toEqualData({});
            //$httpBackend.flush();
            //
            //expect(scope.customers.results).toEqualData(
            //    [
            //        {name: 'My customer'},
            //        {name: 'Other customer'}
            //    ]);
        });

    });

    describe('MailingsCtrl', function () {
        var scope, ctrl, $httpBackend;

        beforeEach(inject(function (_$httpBackend_, $rootScope, $controller) {
            $httpBackend = _$httpBackend_;

            //$httpBackend.expectGET('/api/customers/').
            //    respond({
            //        results: [
            //            {name: 'My customer'},
            //            {name: 'Other customer'}
            //        ]
            //    });
            //
            scope = $rootScope.$new();
            ctrl = $controller('AllMailingsController', {$scope: scope});
        }));


        xit('should get active and finished mailings', function () {
            var data = [{id: 1, domain: 'example.org', status: 'RUNNING'}, {id: 2, domain: 'mailing.org', status: 'PAUSED'}];
            var data2 = [{id: 3, domain: 'example.org', status: 'FINISHED'}];
            $httpBackend.expectGET('/api/mailings?status=FILLING_RECIPIENTS&status=READY&status=RUNNING&status=PAUSED').
                respond({
                    count: 2,
                    results: data
                });
            $httpBackend.expectGET('/api/mailings?status=FINISHED').
                respond({
                    count: 1,
                    results: data2
                });
            $httpBackend.flush();
            expect(scope.finished_mailings.results).toEqualData(data2);
        });

    });
})
;
